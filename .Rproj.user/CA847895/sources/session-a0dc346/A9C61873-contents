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
    QgsProcessingParameterFileDestination,
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
    INPUT_TIME_PER_CREW = 'INPUT_TIME_PER_CREW'
    INPUT_RANK_FIELD = 'INPUT_RANK_FIELD'
    INPUT_RANK_ORDER = 'INPUT_RANK_ORDER'
    OUTPUT_ROUTES = 'OUTPUT_ROUTES'
    OUTPUT_CSV = 'OUTPUT_CSV'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return DoorKnockPlannerAlgorithm()

    def name(self):
        return 'doorknockplanner'

    def displayName(self):
        return self.tr('Door Knock Route Planner')

    def group(self):
        return self.tr('Planning Tools')

    def groupId(self):
        return 'planningtools'

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
        self.addParameter(QgsProcessingParameterNumber(
            self.INPUT_TIME_PER_CREW, self.tr('Time Available per Crew (in hours)'),
            QgsProcessingParameterNumber.Double, defaultValue=8.0, minValue=0.1
        ))
        self.addParameter(QgsProcessingParameterField(
            self.INPUT_RANK_FIELD, self.tr('Optional: Prioritize by Field'),
            parentLayerParameterName=self.INPUT_ADDRESSES,
            type=QgsProcessingParameterField.Numeric, optional=True
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.INPUT_RANK_ORDER, self.tr('Prioritization Order'),
            options=[self.tr('Ascending'), self.tr('Descending')],
            defaultValue=0, optional=True
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_ROUTES, self.tr('Optimized Routes')
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
        self.OUTPUT_CSV, self.tr('Door Knock List (Table)')
        ))

    def processAlgorithm(self, parameters, context, feedback):
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

        rank_field = self.parameterAsString(parameters, self.INPUT_RANK_FIELD, context)
        layer_to_cluster = extracted_layer

        if rank_field:
            feedback.pushInfo(f"Step 2: Prioritizing addresses by field '{rank_field}'...")
            rank_order_asc = self.parameterAsInt(parameters, self.INPUT_RANK_ORDER, context) == 0
            sorted_result = processing.run("native:orderbyexpression", {
                'INPUT': extracted_layer, 'EXPRESSION': f'"{rank_field}"', 'ASCENDING': rank_order_asc, 'OUTPUT': 'memory:'
            }, context=context, feedback=feedback, is_child_algorithm=True)
            layer_to_cluster = QgsProcessingUtils.mapLayerFromString(sorted_result['OUTPUT'], context)
        else:
            feedback.pushInfo("Step 2: Skipping prioritization.")

        feedback.pushInfo(f"Step 3: Dividing {layer_to_cluster.featureCount()} addresses among {num_crews} crews...")
        clustered_result = processing.run("native:kmeansclustering", {
            'INPUT': layer_to_cluster, 'CLUSTERS': num_crews, 'OUTPUT': 'memory:'
        }, context=context, feedback=feedback, is_child_algorithm=True)
        clustered_addresses = QgsProcessingUtils.mapLayerFromString(clustered_result['OUTPUT'], context)

        feedback.pushInfo("Step 4: Preparing final output...")

        # Define fields for the ROUTES output
        route_fields = QgsFields()
        route_fields.append(QgsField('crew_id', QVariant.Int))
        route_fields.append(QgsField('visit_order', QVariant.Int))
        for field in address_layer.fields():
            route_fields.append(field)
        route_fields.append(QgsField('cost', QVariant.Double))
        
        # Define fields for the TABLE (CSV) output
        table_fields = QgsFields()
        table_fields.append(QgsField('crew_id', QVariant.Int))
        table_fields.append(QgsField('visit_order', QVariant.Int))
        for field in address_layer.fields():
            table_fields.append(field)
        
        (routes_sink, routes_dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_ROUTES, context, route_fields, QgsWkbTypes.LineString, road_layer.crs()
        )
        
        # Get the sink for the TABLE (CSV) output
        (table_sink, table_dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_CSV, context, table_fields, QgsWkbTypes.NoGeometry, address_layer.crs()
        )

        feedback.pushInfo("Step 5: Calculating routes for each crew...")
        for i in range(num_crews):
            if feedback.isCanceled(): break
            feedback.pushInfo(f"Processing Crew #{i+1}...")

            crew_addresses_result = processing.run("native:extractbyattribute", {
                'INPUT': clustered_addresses, 'FIELD': 'CLUSTER_ID', 'OPERATOR': 0, 'VALUE': i, 'OUTPUT': 'memory:'
            }, context=context, feedback=feedback, is_child_algorithm=True)
            crew_addresses = QgsProcessingUtils.mapLayerFromString(crew_addresses_result['OUTPUT'], context)
            if not crew_addresses or crew_addresses.featureCount() == 0:
                feedback.pushWarning(f"Crew #{i+1} has no addresses assigned. Skipping.")
                continue

            # ... (snapping logic remains the same) ...
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
                'INPUT': road_layer, 'STRATEGY': 0, 'START_POINT': snapped_start_point_str,
                'END_POINTS': crew_addresses, 'OUTPUT': 'memory:'
            }, context=context, feedback=feedback, is_child_algorithm=True)
            temp_route_layer = QgsProcessingUtils.mapLayerFromString(route_result['OUTPUT'], context)

            route_features_unsorted = list(temp_route_layer.getFeatures())
            
            try:
                route_features_sorted = sorted(route_features_unsorted, key=lambda f: f['cost'])
            except KeyError:
                feedback.pushWarning(f"Could not sort routes by cost for Crew #{i+1}. The 'cost' field was not found.")
                continue

            route_features_to_add = []
            table_features_to_add = []
            for visit_order, feature in enumerate(route_features_sorted):
                # --- Create feature for the ROUTES layer ---
                route_feature = QgsFeature(route_fields)
                route_feature.setGeometry(feature.geometry())
                route_feature.setAttribute('crew_id', i + 1)
                route_feature.setAttribute('visit_order', visit_order + 1)
                route_feature.setAttribute('cost', feature['cost'])
                
                # --- Create feature for the TABLE layer ---
                table_feature = QgsFeature(table_fields)
                table_feature.setAttribute('crew_id', i + 1)
                table_feature.setAttribute('visit_order', visit_order + 1)
                
                for field in address_layer.fields():
                    field_name = field.name()
                    route_feature.setAttribute(field_name, feature.attribute(field_name))
                    table_feature.setAttribute(field_name, feature.attribute(field_name))

                route_features_to_add.append(route_feature)
                table_features_to_add.append(table_feature)

            if route_features_to_add:
                routes_sink.addFeatures(route_features_to_add)
                table_sink.addFeatures(table_features_to_add)
            else:
                feedback.pushWarning(f"No routes could be calculated for Crew #{i+1}.")

        # The framework will handle file creation and loading. We just return the destination IDs.
        return {self.OUTPUT_ROUTES: routes_dest_id, self.OUTPUT_CSV: table_dest_id}
