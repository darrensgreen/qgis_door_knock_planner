# -*- coding: utf-8 -*-
"""
/***************************************************************************
 * *
 * This program is free software; you can redistribute it and/or modify  *
 * it under the terms of the GNU General Public License as published by  *
 * the Free Software Foundation; either version 2 of the License, or     *
 * (at your option) any later version.                                   *
 * *
 ***************************************************************************/
"""

__author__ = 'Darren Green'
__date__ = '2025-09-25'
__copyright__ = '(C) 2025 by Darren Green'

import csv
import processing
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterPoint,
    QgsProcessingParameterVectorLayer,
    QgsProcessingUtils,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsFeatureSink
)


class DoorKnockPlannerAlgorithm(QgsProcessingAlgorithm):
    """
    This algorithm plans door-knocking routes for multiple crews.
    """
    INPUT_POLYGON = 'INPUT_POLYGON'
    INPUT_ADDRESSES = 'INPUT_ADDRESSES'
    INPUT_ROADS = 'INPUT_ROADS'
    INPUT_START_POINT = 'INPUT_START_POINT'
    INPUT_NUM_CREWS = 'INPUT_NUM_CREWS'
    OUTPUT_VISIT_POINTS = 'OUTPUT_VISIT_POINTS' 
    OUTPUT_CSV = 'OUTPUT_CSV'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return DoorKnockPlannerAlgorithm()

    def name(self):
        return 'doorknockplanner'

    def displayName(self):
        return self.tr('Door Knock Route Planner')

    # MODIFIED - Removed group to place algorithm at provider root
    def group(self):
        return ''

    def groupId(self):
        return ''

    def shortHelpString(self):
        return self.tr("Automates the planning of door-knocking campaigns.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT_POLYGON, self.tr('Area of Interest (Polygon)'),
            [QgsProcessing.TypeVectorPolygon]
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT_ADDRESSES, self.tr('Address Points'),
            [QgsProcessing.TypeVectorPoint]
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT_ROADS, self.tr('Road Network'),
            [QgsProcessing.TypeVectorLine]
        ))
        self.addParameter(QgsProcessingParameterPoint(
            self.INPUT_START_POINT, self.tr('Start Location')
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.INPUT_NUM_CREWS, self.tr('Number of Available Crews'),
            QgsProcessingParameterNumber.Integer, defaultValue=1, minValue=1
        ))
        
        # MODIFIED - Changed parameter name and description
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_VISIT_POINTS, self.tr('Visit Points (Ordered)')
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_CSV, self.tr('Door Knock List (Table)')
        ))

    def processAlgorithm(self, parameters, context, feedback):
        """
        Main algorithm execution method.
        """
        try:
            # --- Step 1: Parameter Retrieval and Address Extraction ---
            feedback.pushInfo("Step 1: Initializing and extracting addresses...")

            polygon_layer = self.parameterAsVectorLayer(parameters, self.INPUT_POLYGON, context)
            address_layer = self.parameterAsVectorLayer(parameters, self.INPUT_ADDRESSES, context)
            road_layer = self.parameterAsVectorLayer(parameters, self.INPUT_ROADS, context)
            start_point = self.parameterAsPoint(parameters, self.INPUT_START_POINT, context)
            num_crews = self.parameterAsInt(parameters, self.INPUT_NUM_CREWS, context)

            project_crs = QgsProject.instance().crs()

            if not polygon_layer or not address_layer or not road_layer:
                raise QgsProcessingException("One or more input layers are invalid.")

            extract_result = processing.run("native:extractbylocation", {
                'INPUT': address_layer, 'PREDICATE': [0], 'INTERSECT': polygon_layer, 'OUTPUT': 'memory:'
            }, context=context, feedback=feedback, is_child_algorithm=True)

            extracted_layer = QgsProcessingUtils.mapLayerFromString(extract_result['OUTPUT'], context)
            
            if not extracted_layer or extracted_layer.featureCount() == 0:
                raise QgsProcessingException("No addresses found in the area of interest.")

            # --- Step 2: Divide Addresses into Clusters for Each Crew ---
            feedback.pushInfo(f"Step 2: Dividing {extracted_layer.featureCount()} addresses among {num_crews} crews...")
            
            clustered_result = processing.run("native:kmeansclustering", {
                'INPUT': extracted_layer, 'CLUSTERS': num_crews, 'OUTPUT': 'memory:'
            }, context=context, feedback=feedback, is_child_algorithm=True)
            
            clustered_addresses = QgsProcessingUtils.mapLayerFromString(clustered_result['OUTPUT'], context)

            if not clustered_addresses:
                raise QgsProcessingException("Failed to create clustered addresses layer from K-Means output.")

            # --- Step 3: Prepare Final Output Layers (Sinks) ---
            feedback.pushInfo("Step 3: Preparing final output layers...")

            point_fields = QgsFields()
            point_fields.append(QgsField('crew_id', QVariant.Int))
            point_fields.append(QgsField('visit_order', QVariant.Int))
            for field in address_layer.fields():
                point_fields.append(field)
            point_fields.append(QgsField('cost', QVariant.Double))

            table_fields = QgsFields()
            table_fields.append(QgsField('crew_id', QVariant.Int))
            table_fields.append(QgsField('visit_order', QVariant.Int))
            for field in address_layer.fields():
                table_fields.append(field)

            (points_sink, points_dest_id) = self.parameterAsSink(
                parameters, self.OUTPUT_VISIT_POINTS, context, point_fields, QgsWkbTypes.Point, address_layer.crs()
            )

            (table_sink, table_dest_id) = self.parameterAsSink(
                parameters, self.OUTPUT_CSV, context, table_fields, QgsWkbTypes.NoGeometry, address_layer.crs()
            )

            # --- Step 4: Calculate Ordered Route for Each Crew ---
            feedback.pushInfo("Step 4: Calculating routes for each crew...")
            
            for i in range(num_crews):
                if feedback.isCanceled():
                    break
                feedback.pushInfo(f"Processing Crew #{i+1}...")

                crew_addresses_result = processing.run("native:extractbyattribute", {
                    'INPUT': clustered_addresses, 'FIELD': 'CLUSTER_ID', 'OPERATOR': 0, 'VALUE': i, 'OUTPUT': 'memory:'
                }, context=context, feedback=feedback, is_child_algorithm=True)
                
                crew_addresses = QgsProcessingUtils.mapLayerFromString(crew_addresses_result['OUTPUT'], context)
                
                if not crew_addresses or crew_addresses.featureCount() == 0:
                    feedback.pushWarning(f"Crew #{i+1} has no addresses assigned. Skipping.")
                    continue

                start_point_layer = QgsVectorLayer(f"Point?crs={project_crs.authid()}", f"start_point_temp_{i}", "memory")
                provider = start_point_layer.dataProvider()
                feat = QgsFeature()
                feat.setGeometry(QgsGeometry.fromPointXY(start_point))
                provider.addFeatures([feat])
                
                snapped_point_result = processing.run("qgis:snapgeometries", {
                    'INPUT': start_point_layer, 'REFERENCE_LAYER': road_layer,
                    'TOLERANCE': 1000, 'BEHAVIOR': 0, 'OUTPUT': 'memory:'
                }, context=context, feedback=feedback, is_child_algorithm=True)
                
                snapped_layer = QgsProcessingUtils.mapLayerFromString(snapped_point_result['OUTPUT'], context)
                snapped_feature = next(snapped_layer.getFeatures(), None)
                
                if not snapped_feature:
                    raise QgsProcessingException(f"Could not snap start point for Crew #{i+1}.")
                
                snapped_geom = snapped_feature.geometry()
                road_crs = road_layer.crs()
                if project_crs.authid() != road_crs.authid():
                    transform = QgsCoordinateTransform(project_crs, road_crs, QgsProject.instance())
                    snapped_geom.transform(transform)
                
                snapped_start_point_str = f'{snapped_geom.asPoint().x()},{snapped_geom.asPoint().y()} [{road_crs.authid()}]'

                route_result = processing.run("qgis:shortestpathpointtolayer", {
                    'INPUT': road_layer, 'STRATEGY': 0,
                    'START_POINT': snapped_start_point_str,
                    'END_POINTS': crew_addresses,
                    'OUTPUT': 'memory:'
                }, context=context, feedback=feedback, is_child_algorithm=True)
                
                temp_route_layer = QgsProcessingUtils.mapLayerFromString(route_result['OUTPUT'], context)

                if not temp_route_layer:
                    feedback.pushWarning(f"Route calculation failed for Crew #{i+1}.")
                    continue

                route_features_unsorted = list(temp_route_layer.getFeatures())
                
                try:
                    route_features_sorted = sorted(route_features_unsorted, key=lambda f: f['cost'])
                except KeyError:
                    feedback.pushWarning(f"Could not sort routes by cost for Crew #{i+1}. The 'cost' field was not found.")
                    continue

                point_features_to_add = []
                table_features_to_add = []
                for visit_order, feature in enumerate(route_features_sorted):
                    point_feature = QgsFeature(point_fields)
                    
                    line_geom = feature.geometry()
                    if line_geom and not line_geom.isEmpty():
                        points = line_geom.asPolyline()
                        if points:
                            end_point_geom = QgsGeometry.fromPointXY(points[-1])
                            point_feature.setGeometry(end_point_geom)

                    point_feature.setAttribute('crew_id', i + 1)
                    point_feature.setAttribute('visit_order', visit_order + 1)
                    point_feature.setAttribute('cost', feature['cost'])
                    
                    table_feature = QgsFeature(table_fields)
                    table_feature.setAttribute('crew_id', i + 1)
                    table_feature.setAttribute('visit_order', visit_order + 1)
                    
                    for field in address_layer.fields():
                        field_name = field.name()
                        point_feature.setAttribute(field_name, feature.attribute(field_name))
                        table_feature.setAttribute(field_name, feature.attribute(field_name))

                    point_features_to_add.append(point_feature)
                    table_features_to_add.append(table_feature)

                if point_features_to_add:
                    points_sink.addFeatures(point_features_to_add)
                    table_sink.addFeatures(table_features_to_add)
                else:
                    feedback.pushWarning(f"No routes could be calculated for Crew #{i+1}.")

            return {self.OUTPUT_VISIT_POINTS: points_dest_id, self.OUTPUT_CSV: table_dest_id}

        except Exception as e:
            # This will catch any unexpected error and report it clearly in the log
            feedback.reportError(f"An unexpected error occurred: {e}", fatalError=True)
            import traceback
            feedback.pushDebugInfo(traceback.format_exc())
            return {} # Return an empty dictionary to avoid the TypeError
