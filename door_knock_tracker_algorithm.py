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
__date__ = '2025-10-07'
__copyright__ = '(C) 2025 by Darren Green'

import csv
# MODIFIED: QVariant is part of PyQt.QtCore, not qgis.core
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFeatureSink,
    QgsFeatureSink,
    QgsProcessingUtils,
    QgsFeature,
    QgsVectorLayer,
    QgsFields,
    QgsField,
    # MODIFIED: QVariant removed from this list
)

class DoorKnockTrackerAlgorithm(QgsProcessingAlgorithm):
    INPUT_CSVS = 'INPUT_CSVS'
    INPUT_ORIGINAL_POINTS = 'INPUT_ORIGINAL_POINTS'
    INPUT_NEW_POINTS = 'INPUT_NEW_POINTS'
    INPUT_UNIQUE_ID = 'INPUT_UNIQUE_ID'
    OUTPUT_NEXT_PRIORITY = 'OUTPUT_NEXT_PRIORITY'
    OUTPUT_EXCEPTIONS = 'OUTPUT_EXCEPTIONS'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return DoorKnockTrackerAlgorithm()

    def name(self):
        return 'doorknocktracker'

    def displayName(self):
        return self.tr('Door Knock Status Tracker')

    def group(self):
        return ''

    def groupId(self):
        return ''

    def shortHelpString(self):
        return self.tr("Combines completed field data (CSVs) with original and new address lists to produce a single layer of outstanding properties to visit.")

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT_CSVS, self.tr('Completed Crew CSV Files'), QgsProcessing.TypeVector
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_ORIGINAL_POINTS, self.tr('Original Visit Points Layer'), [QgsProcessing.TypeVectorPoint]
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_NEW_POINTS, self.tr('New Address Layer'), [QgsProcessing.TypeVectorPoint], optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.INPUT_UNIQUE_ID, self.tr('Unique Address ID Field'), parentLayerParameterName=self.INPUT_ORIGINAL_POINTS
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_NEXT_PRIORITY, self.tr('Next Priority Addresses')
            )
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_EXCEPTIONS, self.tr('Validation Exception Report (Optional)'), 'CSV files (*.csv)', optional=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        feedback.pushInfo("Step 1: Reading input parameters...")
        csv_layers = self.parameterAsLayerList(parameters, self.INPUT_CSVS, context)
        original_points_layer = self.parameterAsVectorLayer(parameters, self.INPUT_ORIGINAL_POINTS, context)
        new_points_layer = self.parameterAsVectorLayer(parameters, self.INPUT_NEW_POINTS, context)
        unique_id_field = self.parameterAsString(parameters, self.INPUT_UNIQUE_ID, context)
        exception_report_path = self.parameterAsFileOutput(parameters, self.OUTPUT_EXCEPTIONS, context)

        id_field_index = original_points_layer.fields().indexOf(unique_id_field)
        if id_field_index == -1:
            raise QgsProcessingException(f"Unique ID field '{unique_id_field}' not found in the original points layer.")
        is_numeric_id = original_points_layer.fields().at(id_field_index).isNumeric()

        def normalize_key(val):
            if val is None: return None
            if is_numeric_id:
                try: return int(float(val))
                except (ValueError, TypeError): return None
            else: return str(val).strip().lower()

        feedback.pushInfo("Step 2: Processing crew CSVs to find best available status...")
        best_status = {}
        
        validation_fields = ['Inquiry Date', 'Inquirer ID', 'Inquirer Org']

        for i, csv_layer in enumerate(csv_layers):
            feedback.pushInfo(f" -> Reading CSV {i+1}/{len(csv_layers)}: {csv_layer.name()}")
            csv_fields = csv_layer.fields().names()
            if unique_id_field not in csv_fields or 'Outcome' not in csv_fields:
                feedback.pushWarning(f"Skipping CSV '{csv_layer.name()}' because it is missing '{unique_id_field}' or 'Outcome'.")
                continue

            for feature in csv_layer.getFeatures():
                unique_id = normalize_key(feature.attribute(unique_id_field))
                if unique_id is None: continue

                new_outcome = feature.attribute('Outcome')
                new_status = { 'outcome': new_outcome }
                for field in validation_fields:
                    new_status[field] = feature.attribute(field) if field in csv_fields else None
                
                stored_status = best_status.get(unique_id)
                if not stored_status or (stored_status.get('outcome', '').strip().lower() != 'completed'):
                    best_status[unique_id] = new_status

        feedback.pushInfo(f"Found best available status for {len(best_status)} unique properties from CSVs.")

        feedback.pushInfo("Step 3: Combining all source address layers...")
        master_features = {}
        for feature in original_points_layer.getFeatures():
            unique_id = normalize_key(feature.attribute(unique_id_field))
            if unique_id is not None: master_features[unique_id] = feature
        
        if new_points_layer:
            feedback.pushInfo(" -> Adding new addresses from optional layer...")
            for feature in new_points_layer.getFeatures():
                unique_id = normalize_key(feature.attribute(unique_id_field))
                if unique_id is not None and unique_id not in master_features:
                    master_features[unique_id] = feature
        
        feedback.pushInfo(f"Created a master list of {len(master_features)} unique addresses.")
        
        feedback.pushInfo("Step 4: Filtering for priority addresses and generating exception report...")
        features_to_add = []
        exception_records = []
        match_count = 0
        
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT_NEXT_PRIORITY, context, original_points_layer.fields(), original_points_layer.wkbType(), original_points_layer.crs())

        for unique_id, feature in master_features.items():
            status_record = best_status.get(unique_id)
            is_priority = True
            
            if status_record:
                match_count += 1
                outcome = status_record.get('outcome')
                
                if outcome and str(outcome).strip().lower() == 'completed':
                    is_valid_completion = True
                    missing_fields = []
                    for field in validation_fields:
                        val = status_record.get(field)
                        if val is None or str(val).strip() == '':
                            is_valid_completion = False
                            missing_fields.append(field)
                    
                    if is_valid_completion:
                        is_priority = False
                    else:
                        is_priority = True
                        exception_reason = f"Marked 'Completed' but missing data in: {', '.join(missing_fields)}"
                        exception_records.append([feature.attribute(unique_id_field), exception_reason])
            
            if is_priority:
                new_feat = QgsFeature(original_points_layer.fields())
                new_feat.setGeometry(feature.geometry())
                for fld in original_points_layer.fields().names():
                    new_feat.setAttribute(fld, feature.attribute(fld))
                features_to_add.append(new_feat)
        
        feedback.pushInfo(f"Successfully matched status for {match_count} of {len(master_features)} addresses.")
        if match_count == 0 and len(best_status) > 0:
            feedback.pushWarning("Warning: No addresses from the CSV files could be matched to the source layers. Please check the 'Unique Address ID Field'.")
        
        feedback.pushInfo(f"Found {len(features_to_add)} priority addresses for the next shift.")
        if features_to_add:
            sink.addFeatures(features_to_add, QgsFeatureSink.FastInsert)

        if exception_report_path and exception_records:
            feedback.pushInfo(f"Writing {len(exception_records)} records to exception report...")
            try:
                with open(exception_report_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([unique_id_field, 'Reason'])
                    writer.writerows(exception_records)
            except Exception as e:
                feedback.pushWarning(f"Could not write exception report: {e}")

        return {self.OUTPUT_NEXT_PRIORITY: dest_id, self.OUTPUT_EXCEPTIONS: exception_report_path if exception_records else ''}
