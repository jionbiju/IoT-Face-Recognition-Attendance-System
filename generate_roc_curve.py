#!/usr/bin/env python3
"""
ROC Curve Analysis for Face Recognition System
Evaluates the performance of the face recognition model
"""

import os
import cv2
import numpy as np
import pickle
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, auc, confusion_matrix, classification_report
from sklearn.metrics.pairwise import cosine_similarity
import seaborn as sns
from datetime import datetime

# Import face recognition model (FaceNet - the one actually used in production)
from facenet_model import face_recognizer

# Paths
DATASET_DIR = "dataset"
MODEL_PATH = "face_encodings.pkl"
OUTPUT_DIR = "roc_analysis"

os.makedirs(OUTPUT_DIR, exist_ok=True)

class ROCAnalyzer:
    def __init__(self):
        self.face_recognizer = face_recognizer
        self.true_labels = []
        self.predicted_scores = []
        self.predicted_labels = []
        self.student_ids = []
        
    def load_test_data(self):
        """Load test data from dataset directory"""
        print("Loading test data from dataset...")
        
        if not os.path.exists(DATASET_DIR):
            print(f"Error: Dataset directory '{DATASET_DIR}' not found!")
            return False
        
        student_folders = [f for f in os.listdir(DATASET_DIR) 
                          if os.path.isdir(os.path.join(DATASET_DIR, f))]
        
        if not student_folders:
            print("Error: No student folders found in dataset!")
            return False
        
        print(f"Found {len(student_folders)} students in dataset")
        
        # For each student, use 80% for training reference, 20% for testing
        for folder_name in student_folders:
            try:
                student_id = int(folder_name)
                folder_path = os.path.join(DATASET_DIR, folder_name)
                
                image_files = [f for f in os.listdir(folder_path) 
                              if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                
                if len(image_files) < 5:
                    print(f"Skipping student {student_id}: insufficient images ({len(image_files)})")
                    continue
                
                # Split into train and test
                np.random.shuffle(image_files)
                split_idx = int(len(image_files) * 0.8)
                test_images = image_files[split_idx:]
                
                print(f"Student {student_id}: Testing with {len(test_images)} images")
                
                # Process test images
                for img_file in test_images:
                    img_path = os.path.join(folder_path, img_file)
                    
                    # Extract encoding
                    encoding = self.face_recognizer.extract_face_encoding(img_path)
                    
                    if encoding is not None:
                        # Get prediction
                        pred_id, confidence, is_match = self.face_recognizer.predict_face(encoding)
                        
                        # Store results
                        self.true_labels.append(student_id)
                        self.predicted_scores.append(confidence)
                        self.predicted_labels.append(pred_id if pred_id is not None else -1)
                        self.student_ids.append(student_id)
                
            except ValueError:
                continue
        
        print(f"\nTotal test samples: {len(self.true_labels)}")
        return len(self.true_labels) > 0
    
    def generate_binary_roc(self):
        """Generate ROC curve for binary classification (genuine vs impostor)"""
        print("\nGenerating Binary ROC Curve...")
        
        # Convert to binary: 1 if correct match, 0 if wrong match
        y_true_binary = []
        y_scores = []
        
        for i in range(len(self.true_labels)):
            true_id = self.true_labels[i]
            pred_id = self.predicted_labels[i]
            score = self.predicted_scores[i]
            
            # Binary label: 1 if correct, 0 if incorrect
            y_true_binary.append(1 if true_id == pred_id else 0)
            y_scores.append(score)
        
        # Calculate ROC curve
        fpr, tpr, thresholds = roc_curve(y_true_binary, y_scores)
        roc_auc = auc(fpr, tpr)
        
        # Find optimal threshold (Youden's J statistic)
        j_scores = tpr - fpr
        optimal_idx = np.argmax(j_scores)
        optimal_threshold = thresholds[optimal_idx]
        optimal_tpr = tpr[optimal_idx]
        optimal_fpr = fpr[optimal_idx]
        
        # Plot ROC curve
        plt.figure(figsize=(10, 8))
        plt.plot(fpr, tpr, color='darkorange', lw=2, 
                label=f'ROC curve (AUC = {roc_auc:.3f})')
        plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--', 
                label='Random Classifier')
        plt.scatter([optimal_fpr], [optimal_tpr], marker='o', color='red', s=100, 
                   label=f'Optimal Threshold = {optimal_threshold:.3f}')
        
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.05])
        plt.xlabel('False Positive Rate (FPR)', fontsize=12)
        plt.ylabel('True Positive Rate (TPR)', fontsize=12)
        plt.title('ROC Curve - Face Recognition System', fontsize=14, fontweight='bold')
        plt.legend(loc="lower right", fontsize=10)
        plt.grid(True, alpha=0.3)
        
        # Save plot
        roc_path = os.path.join(OUTPUT_DIR, 'roc_curve.png')
        plt.savefig(roc_path, dpi=300, bbox_inches='tight')
        print(f"✓ ROC curve saved to: {roc_path}")
        plt.close()
        
        return {
            'auc': roc_auc,
            'optimal_threshold': optimal_threshold,
            'optimal_tpr': optimal_tpr,
            'optimal_fpr': optimal_fpr,
            'fpr': fpr,
            'tpr': tpr,
            'thresholds': thresholds
        }
    
    def generate_multiclass_analysis(self):
        """Generate multi-class confusion matrix and metrics"""
        print("\nGenerating Multi-class Analysis...")
        
        # Get unique student IDs
        unique_students = sorted(set(self.true_labels))
        
        # Create confusion matrix
        cm = confusion_matrix(self.true_labels, self.predicted_labels, 
                             labels=unique_students)
        
        # Plot confusion matrix
        plt.figure(figsize=(12, 10))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
                   xticklabels=unique_students, yticklabels=unique_students,
                   cbar_kws={'label': 'Count'})
        plt.xlabel('Predicted Student ID', fontsize=12)
        plt.ylabel('True Student ID', fontsize=12)
        plt.title('Confusion Matrix - Face Recognition', fontsize=14, fontweight='bold')
        
        cm_path = os.path.join(OUTPUT_DIR, 'confusion_matrix.png')
        plt.savefig(cm_path, dpi=300, bbox_inches='tight')
        print(f"✓ Confusion matrix saved to: {cm_path}")
        plt.close()
        
        # Calculate per-class metrics
        report = classification_report(self.true_labels, self.predicted_labels, 
                                      labels=unique_students, output_dict=True, 
                                      zero_division=0)
        
        return {
            'confusion_matrix': cm,
            'classification_report': report,
            'unique_students': unique_students
        }
    
    def generate_score_distribution(self):
        """Generate score distribution plots"""
        print("\nGenerating Score Distribution...")
        
        # Separate genuine and impostor scores
        genuine_scores = []
        impostor_scores = []
        
        for i in range(len(self.true_labels)):
            true_id = self.true_labels[i]
            pred_id = self.predicted_labels[i]
            score = self.predicted_scores[i]
            
            if true_id == pred_id:
                genuine_scores.append(score)
            else:
                impostor_scores.append(score)
        
        # Plot distributions
        plt.figure(figsize=(12, 6))
        
        plt.subplot(1, 2, 1)
        plt.hist(genuine_scores, bins=30, alpha=0.7, color='green', edgecolor='black')
        plt.xlabel('Confidence Score', fontsize=11)
        plt.ylabel('Frequency', fontsize=11)
        plt.title('Genuine Match Score Distribution', fontsize=12, fontweight='bold')
        plt.axvline(np.mean(genuine_scores), color='darkgreen', linestyle='--', 
                   linewidth=2, label=f'Mean = {np.mean(genuine_scores):.3f}')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        plt.subplot(1, 2, 2)
        plt.hist(impostor_scores, bins=30, alpha=0.7, color='red', edgecolor='black')
        plt.xlabel('Confidence Score', fontsize=11)
        plt.ylabel('Frequency', fontsize=11)
        plt.title('Impostor Match Score Distribution', fontsize=12, fontweight='bold')
        if impostor_scores:
            plt.axvline(np.mean(impostor_scores), color='darkred', linestyle='--', 
                       linewidth=2, label=f'Mean = {np.mean(impostor_scores):.3f}')
            plt.legend()
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        dist_path = os.path.join(OUTPUT_DIR, 'score_distribution.png')
        plt.savefig(dist_path, dpi=300, bbox_inches='tight')
        print(f"✓ Score distribution saved to: {dist_path}")
        plt.close()
        
        return {
            'genuine_scores': genuine_scores,
            'impostor_scores': impostor_scores,
            'genuine_mean': np.mean(genuine_scores) if genuine_scores else 0,
            'impostor_mean': np.mean(impostor_scores) if impostor_scores else 0
        }
    
    def generate_det_curve(self, roc_data):
        """Generate Detection Error Tradeoff (DET) curve"""
        print("\nGenerating DET Curve...")
        
        fpr = roc_data['fpr']
        fnr = 1 - roc_data['tpr']  # False Negative Rate
        
        plt.figure(figsize=(10, 8))
        plt.plot(fpr * 100, fnr * 100, color='blue', lw=2)
        plt.xlabel('False Positive Rate (%)', fontsize=12)
        plt.ylabel('False Negative Rate (%)', fontsize=12)
        plt.title('Detection Error Tradeoff (DET) Curve', fontsize=14, fontweight='bold')
        plt.grid(True, alpha=0.3)
        plt.xlim([0, 100])
        plt.ylim([0, 100])
        
        # Mark Equal Error Rate (EER)
        eer_idx = np.argmin(np.abs(fpr - fnr))
        eer = (fpr[eer_idx] + fnr[eer_idx]) / 2
        plt.scatter([fpr[eer_idx] * 100], [fnr[eer_idx] * 100], 
                   marker='o', color='red', s=100, 
                   label=f'EER = {eer * 100:.2f}%')
        plt.legend(fontsize=10)
        
        det_path = os.path.join(OUTPUT_DIR, 'det_curve.png')
        plt.savefig(det_path, dpi=300, bbox_inches='tight')
        print(f"✓ DET curve saved to: {det_path}")
        plt.close()
        
        return {'eer': eer}
    
    def generate_report(self, roc_data, multiclass_data, score_data, det_data):
        """Generate comprehensive text report"""
        print("\nGenerating Analysis Report...")
        
        report_path = os.path.join(OUTPUT_DIR, 'analysis_report.txt')
        
        with open(report_path, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("FACE RECOGNITION SYSTEM - ROC ANALYSIS REPORT\n")
            f.write("=" * 80 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Test Samples: {len(self.true_labels)}\n")
            f.write(f"Number of Students: {len(set(self.true_labels))}\n")
            f.write("\n")
            
            f.write("-" * 80 + "\n")
            f.write("1. ROC CURVE ANALYSIS\n")
            f.write("-" * 80 + "\n")
            f.write(f"Area Under Curve (AUC): {roc_data['auc']:.4f}\n")
            f.write(f"Optimal Threshold: {roc_data['optimal_threshold']:.4f}\n")
            f.write(f"True Positive Rate at Optimal: {roc_data['optimal_tpr']:.4f}\n")
            f.write(f"False Positive Rate at Optimal: {roc_data['optimal_fpr']:.4f}\n")
            f.write(f"Equal Error Rate (EER): {det_data['eer'] * 100:.2f}%\n")
            f.write("\n")
            
            f.write("-" * 80 + "\n")
            f.write("2. SCORE DISTRIBUTION ANALYSIS\n")
            f.write("-" * 80 + "\n")
            f.write(f"Genuine Match Scores:\n")
            f.write(f"  Count: {len(score_data['genuine_scores'])}\n")
            f.write(f"  Mean: {score_data['genuine_mean']:.4f}\n")
            if score_data['genuine_scores']:
                f.write(f"  Std Dev: {np.std(score_data['genuine_scores']):.4f}\n")
                f.write(f"  Min: {np.min(score_data['genuine_scores']):.4f}\n")
                f.write(f"  Max: {np.max(score_data['genuine_scores']):.4f}\n")
            f.write(f"\nImpostor Match Scores:\n")
            f.write(f"  Count: {len(score_data['impostor_scores'])}\n")
            if score_data['impostor_scores']:
                f.write(f"  Mean: {score_data['impostor_mean']:.4f}\n")
                f.write(f"  Std Dev: {np.std(score_data['impostor_scores']):.4f}\n")
                f.write(f"  Min: {np.min(score_data['impostor_scores']):.4f}\n")
                f.write(f"  Max: {np.max(score_data['impostor_scores']):.4f}\n")
            f.write("\n")
            
            f.write("-" * 80 + "\n")
            f.write("3. CLASSIFICATION METRICS\n")
            f.write("-" * 80 + "\n")
            report = multiclass_data['classification_report']
            f.write(f"Overall Accuracy: {report['accuracy']:.4f}\n")
            f.write(f"Macro Average Precision: {report['macro avg']['precision']:.4f}\n")
            f.write(f"Macro Average Recall: {report['macro avg']['recall']:.4f}\n")
            f.write(f"Macro Average F1-Score: {report['macro avg']['f1-score']:.4f}\n")
            f.write("\n")
            
            f.write("-" * 80 + "\n")
            f.write("4. PER-STUDENT PERFORMANCE\n")
            f.write("-" * 80 + "\n")
            f.write(f"{'Student ID':<12} {'Precision':<12} {'Recall':<12} {'F1-Score':<12} {'Support':<12}\n")
            f.write("-" * 80 + "\n")
            for student_id in multiclass_data['unique_students']:
                student_key = str(student_id)
                if student_key in report:
                    metrics = report[student_key]
                    f.write(f"{student_id:<12} {metrics['precision']:<12.4f} "
                           f"{metrics['recall']:<12.4f} {metrics['f1-score']:<12.4f} "
                           f"{int(metrics['support']):<12}\n")
            f.write("\n")
            
            f.write("-" * 80 + "\n")
            f.write("5. INTERPRETATION\n")
            f.write("-" * 80 + "\n")
            
            # Interpret AUC
            auc_val = roc_data['auc']
            if auc_val >= 0.95:
                auc_interp = "Excellent"
            elif auc_val >= 0.90:
                auc_interp = "Very Good"
            elif auc_val >= 0.80:
                auc_interp = "Good"
            elif auc_val >= 0.70:
                auc_interp = "Fair"
            else:
                auc_interp = "Poor"
            
            f.write(f"AUC Interpretation: {auc_interp} ({auc_val:.4f})\n")
            f.write(f"  - The model can distinguish between genuine and impostor matches\n")
            f.write(f"    with {auc_interp.lower()} accuracy.\n\n")
            
            f.write(f"Recommended Operating Threshold: {roc_data['optimal_threshold']:.4f}\n")
            f.write(f"  - At this threshold:\n")
            f.write(f"    * {roc_data['optimal_tpr'] * 100:.1f}% of genuine users will be accepted\n")
            f.write(f"    * {roc_data['optimal_fpr'] * 100:.1f}% of impostors will be falsely accepted\n\n")
            
            f.write("=" * 80 + "\n")
        
        print(f"✓ Analysis report saved to: {report_path}")
    
    def run_full_analysis(self):
        """Run complete ROC analysis"""
        print("\n" + "=" * 80)
        print("FACE RECOGNITION SYSTEM - ROC CURVE ANALYSIS")
        print("=" * 80 + "\n")
        
        # Load test data
        if not self.load_test_data():
            print("Error: Failed to load test data!")
            return False
        
        # Generate analyses
        roc_data = self.generate_binary_roc()
        multiclass_data = self.generate_multiclass_analysis()
        score_data = self.generate_score_distribution()
        det_data = self.generate_det_curve(roc_data)
        
        # Generate report
        self.generate_report(roc_data, multiclass_data, score_data, det_data)
        
        print("\n" + "=" * 80)
        print("ANALYSIS COMPLETE!")
        print("=" * 80)
        print(f"\nResults saved in: {OUTPUT_DIR}/")
        print(f"  - roc_curve.png")
        print(f"  - confusion_matrix.png")
        print(f"  - score_distribution.png")
        print(f"  - det_curve.png")
        print(f"  - analysis_report.txt")
        print(f"\nKey Metrics:")
        print(f"  AUC: {roc_data['auc']:.4f}")
        print(f"  Optimal Threshold: {roc_data['optimal_threshold']:.4f}")
        print(f"  EER: {det_data['eer'] * 100:.2f}%")
        print(f"  Accuracy: {multiclass_data['classification_report']['accuracy']:.4f}")
        
        return True

if __name__ == "__main__":
    analyzer = ROCAnalyzer()
    analyzer.run_full_analysis()
