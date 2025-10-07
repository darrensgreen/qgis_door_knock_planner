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
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
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
    QgsField
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
                self.OUTPUT_NEXT_PRIORITY, self.tr('Updated Visit Points')
            )
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_EXCEPTIONS, self.tr('Validation Exception Report'), 'CSV files (*.csv)', optional=True
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
        tracking_fields = ['Inquiry Date', 'Inquirer ID', 'Inquirer Org', 'Notes', 'Outcome']

        for i, csv_layer in enumerate(csv_layers):
            feedback.pushInfo(f" -> Reading CSV {i+1}/{len(csv_layers)}: {csv_layer.name()}")
            csv_fields = csv_layer.fields().names()
            if unique_id_field not in csv_fields or 'Outcome' not in csv_fields:
                feedback.pushWarning(f"Skipping CSV '{csv_layer.name()}' because it is missing '{unique_id_field}' or 'Outcome'.")
                continue

            for feature in csv_layer.getFeatures():
                unique_id = normalize_key(feature.attribute(unique_id_field))
                if unique_id is None: continue

                new_status = {}
                for field in tracking_fields:
                    new_status[field] = feature.attribute(field) if field in csv_fields else None
                
                stored_status = best_status.get(unique_id)
                if not stored_status or (stored_status.get('Outcome', '').strip().lower() != 'completed'):
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
        
        output_fields = QgsFields()
        for field in original_points_layer.fields():
            if field.name() == 'Inquiry Date':
                output_fields.append(QgsField(field.name(), QVariant.String))
            else:
                output_fields.append(field)
        
        feedback.pushInfo("Step 4: Updating features and generating exception report...")
        updated_features = []
        exception_records = []
        
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT_NEXT_PRIORITY, context, output_fields, original_points_layer.wkbType(), original_points_layer.crs())

        for unique_id, original_feature in master_features.items():
            updated_feature = QgsFeature(output_fields)
            updated_feature.setGeometry(original_feature.geometry())
            
            for field in original_feature.fields():
                 # MODIFIED: Use indexOf() which returns -1 if not found, instead of the incorrect exists()
                 if output_fields.indexOf(field.name()) != -1:
                    updated_feature.setAttribute(field.name(), original_feature.attribute(field.name()))

            status_record = best_status.get(unique_id)

            if status_record:
                outcome_val = status_record.get('Outcome')
                
                if outcome_val and str(outcome_val).strip().lower() == 'completed':
                    is_valid_completion = True
                    missing_fields = []
                    validation_fields = ['Inquiry Date', 'Inquirer ID', 'Inquirer Org']
                    for field in validation_fields:
                        val = status_record.get(field)
                        if val is None or str(val).strip() == '':
                            is_valid_completion = False
                            missing_fields.append(field)
                    
                    if is_valid_completion:
                        for field in tracking_fields:
                            updated_feature.setAttribute(field, status_record.get(field))
                    else:
                        updated_feature.setAttribute('Outcome', 'Outstanding')
                        exception_reason = f"Marked 'Completed' but missing data in: {', '.join(missing_fields)}"
                        exception_records.append([original_feature.attribute(unique_id_field), exception_reason])
                else:
                    for field in tracking_fields:
                        updated_feature.setAttribute(field, status_record.get(field))
            
            updated_features.append(updated_feature)
        
        feedback.pushInfo(f"Processed {len(updated_features)} total addresses for the updated layer.")

        if updated_features:
            sink.addFeatures(updated_features, QgsFeatureSink.FastInsert)

        if exception_report_path and exception_records:
            feedback.pushInfo(f"Writing {len(exception_records)} records to exception report...")
            try:
                with open(exception_report_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([unique_id_field, 'Reason'])
                    writer.writerows(exception_records)
            except Exception as e:
                feedback.pushWarning(f"Could not write exception report: {e}")

        return {self.OUTPUT_NEXT_PRIORITY: dest_id}
