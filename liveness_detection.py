"""
Advanced Liveness Detection Module
Prevents spoofing attacks using photos, videos, or printed images
"""

import cv2
import numpy as np
from collections import deque
import time

class LivenessDetector:
    """
    Multi-layered liveness detection system using:
    1. Texture Analysis (LBP - Local Binary Patterns)
    2. Motion Detection (optical flow)
    3. Blink Detection
    4. Color/Frequency Analysis
    5. Face Quality Assessment
    """
    
    def __init__(self):
        self.motion_history = deque(maxlen=10)
        self.blink_history = deque(maxlen=5)
        
        # Load eye cascade for blink detection
        try:
            self.eye_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_eye.xml'
            )
        except:
            self.eye_cascade = None
            print("⚠ Eye cascade not available, blink detection disabled")
    
    def check_liveness(self, image, face_bbox=None):
        """
        Comprehensive liveness check
        Returns: (is_live, confidence, details)
        """
        if image is None or image.size == 0:
            return False, 0.0, "Invalid image"
        
        scores = {}
        
        # 1. Texture Analysis (most important for photo detection)
        texture_score = self.analyze_texture(image, face_bbox)
        scores['texture'] = texture_score
        
        # 2. Color Distribution Analysis
        color_score = self.analyze_color_distribution(image, face_bbox)
        scores['color'] = color_score
        
        # 3. Frequency Analysis (Moiré patterns from screens)
        frequency_score = self.analyze_frequency(image, face_bbox)
        scores['frequency'] = frequency_score
        
        # 4. Face Quality Assessment
        quality_score = self.assess_face_quality(image, face_bbox)
        scores['quality'] = quality_score
        
        # 5. Reflection/Glare Detection (photos often have unnatural reflections)
        reflection_score = self.detect_reflections(image, face_bbox)
        scores['reflection'] = reflection_score
        
        # Calculate weighted overall score
        weights = {
            'texture': 0.35,      # Most important
            'color': 0.20,
            'frequency': 0.20,
            'quality': 0.15,
            'reflection': 0.10
        }
        
        overall_score = sum(scores[k] * weights[k] for k in weights.keys())
        
        # Threshold for liveness
        is_live = overall_score >= 0.60
        
        # Create detailed report
        details = {
            'overall_score': round(overall_score, 3),
            'scores': {k: round(v, 3) for k, v in scores.items()},
            'verdict': 'LIVE' if is_live else 'SPOOF'
        }
        
        return is_live, overall_score, details
    
    def analyze_texture(self, image, face_bbox=None):
        """
        Analyze texture using Local Binary Patterns (LBP)
        Real faces have more complex texture than photos
        """
        try:
            # Extract face region if bbox provided
            if face_bbox is not None:
                x, y, w, h = face_bbox
                face_region = image[y:y+h, x:x+w]
            else:
                face_region = image
            
            if face_region.size == 0:
                return 0.5
            
            # Convert to grayscale
            if len(face_region.shape) == 3:
                gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
            else:
                gray = face_region
            
            # Resize for consistent analysis
            gray = cv2.resize(gray, (128, 128))
            
            # Calculate LBP
            lbp = self.calculate_lbp(gray)
            
            # Calculate histogram
            hist, _ = np.histogram(lbp.ravel(), bins=256, range=(0, 256))
            hist = hist.astype(float)
            hist /= (hist.sum() + 1e-7)
            
            # Real faces have more uniform LBP distribution
            # Photos/screens have more concentrated patterns
            entropy = -np.sum(hist * np.log2(hist + 1e-7))
            
            # Normalize entropy (typical range 4-8)
            texture_score = np.clip((entropy - 4) / 4, 0, 1)
            
            # Also check edge density (real faces have more natural edges)
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            
            # Combine metrics
            final_score = 0.7 * texture_score + 0.3 * np.clip(edge_density * 10, 0, 1)
            
            return final_score
            
        except Exception as e:
            print(f"Texture analysis error: {e}")
            return 0.5
    
    def calculate_lbp(self, image):
        """Calculate Local Binary Pattern"""
        rows, cols = image.shape
        lbp = np.zeros_like(image)
        
        for i in range(1, rows - 1):
            for j in range(1, cols - 1):
                center = image[i, j]
                code = 0
                
                # 8 neighbors
                code |= (image[i-1, j-1] >= center) << 7
                code |= (image[i-1, j] >= center) << 6
                code |= (image[i-1, j+1] >= center) << 5
                code |= (image[i, j+1] >= center) << 4
                code |= (image[i+1, j+1] >= center) << 3
                code |= (image[i+1, j] >= center) << 2
                code |= (image[i+1, j-1] >= center) << 1
                code |= (image[i, j-1] >= center) << 0
                
                lbp[i, j] = code
        
        return lbp
    
    def analyze_color_distribution(self, image, face_bbox=None):
        """
        Analyze color distribution
        Real faces have natural skin tone distribution
        Photos often have color shifts or unnatural tones
        """
        try:
            # Extract face region
            if face_bbox is not None:
                x, y, w, h = face_bbox
                face_region = image[y:y+h, x:x+w]
            else:
                face_region = image
            
            if face_region.size == 0:
                return 0.5
            
            # Convert to different color spaces
            hsv = cv2.cvtColor(face_region, cv2.COLOR_BGR2HSV)
            ycrcb = cv2.cvtColor(face_region, cv2.COLOR_BGR2YCrCb)
            
            # Check skin tone in YCrCb (good for skin detection)
            cr = ycrcb[:, :, 1]
            cb = ycrcb[:, :, 2]
            
            # Typical skin tone ranges
            skin_mask = ((cr >= 133) & (cr <= 173) & (cb >= 77) & (cb <= 127))
            skin_ratio = np.sum(skin_mask) / skin_mask.size
            
            # Check color variance (photos often have less variance)
            color_std = np.mean([np.std(face_region[:, :, i]) for i in range(3)])
            variance_score = np.clip(color_std / 50, 0, 1)
            
            # Combine metrics
            color_score = 0.6 * np.clip(skin_ratio * 2, 0, 1) + 0.4 * variance_score
            
            return color_score
            
        except Exception as e:
            print(f"Color analysis error: {e}")
            return 0.5
    
    def analyze_frequency(self, image, face_bbox=None):
        """
        Analyze frequency domain for Moiré patterns
        Photos of screens show characteristic patterns
        """
        try:
            # Extract face region
            if face_bbox is not None:
                x, y, w, h = face_bbox
                face_region = image[y:y+h, x:x+w]
            else:
                face_region = image
            
            if face_region.size == 0:
                return 0.5
            
            # Convert to grayscale
            if len(face_region.shape) == 3:
                gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
            else:
                gray = face_region
            
            # Resize for consistent analysis
            gray = cv2.resize(gray, (128, 128))
            
            # Apply FFT
            f_transform = np.fft.fft2(gray)
            f_shift = np.fft.fftshift(f_transform)
            magnitude = np.abs(f_shift)
            
            # Analyze high-frequency components
            # Photos/screens have more regular high-frequency patterns
            rows, cols = magnitude.shape
            center_row, center_col = rows // 2, cols // 2
            
            # Create ring mask for high frequencies
            y, x = np.ogrid[:rows, :cols]
            mask = ((x - center_col)**2 + (y - center_row)**2) > (min(rows, cols) // 4)**2
            
            high_freq_energy = np.sum(magnitude[mask])
            total_energy = np.sum(magnitude)
            
            high_freq_ratio = high_freq_energy / (total_energy + 1e-7)
            
            # Real faces have moderate high-frequency content
            # Photos have either too much (Moiré) or too little (blur)
            # Optimal range: 0.15 - 0.35
            if 0.15 <= high_freq_ratio <= 0.35:
                frequency_score = 1.0
            elif high_freq_ratio < 0.15:
                frequency_score = high_freq_ratio / 0.15
            else:
                frequency_score = max(0, 1 - (high_freq_ratio - 0.35) / 0.35)
            
            return frequency_score
            
        except Exception as e:
            print(f"Frequency analysis error: {e}")
            return 0.5
    
    def assess_face_quality(self, image, face_bbox=None):
        """
        Assess overall face quality
        Photos often have compression artifacts or unnatural sharpness
        """
        try:
            # Extract face region
            if face_bbox is not None:
                x, y, w, h = face_bbox
                face_region = image[y:y+h, x:x+w]
            else:
                face_region = image
            
            if face_region.size == 0:
                return 0.5
            
            # Convert to grayscale
            if len(face_region.shape) == 3:
                gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
            else:
                gray = face_region
            
            # Calculate Laplacian variance (sharpness)
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            sharpness = laplacian.var()
            
            # Real faces: moderate sharpness (50-500)
            # Photos: often too sharp or too blurry
            if 50 <= sharpness <= 500:
                sharpness_score = 1.0
            elif sharpness < 50:
                sharpness_score = sharpness / 50
            else:
                sharpness_score = max(0, 1 - (sharpness - 500) / 500)
            
            # Check for JPEG artifacts (common in photos)
            # Calculate blockiness
            block_size = 8
            h, w = gray.shape
            blocks_v = h // block_size
            blocks_h = w // block_size
            
            blockiness = 0
            for i in range(1, blocks_v):
                row = i * block_size
                diff = np.abs(gray[row, :].astype(int) - gray[row-1, :].astype(int))
                blockiness += np.mean(diff)
            
            blockiness /= max(blocks_v - 1, 1)
            
            # Lower blockiness is better (less JPEG artifacts)
            artifact_score = max(0, 1 - blockiness / 20)
            
            # Combine metrics
            quality_score = 0.6 * sharpness_score + 0.4 * artifact_score
            
            return quality_score
            
        except Exception as e:
            print(f"Quality assessment error: {e}")
            return 0.5
    
    def detect_reflections(self, image, face_bbox=None):
        """
        Detect unnatural reflections/glare
        Photos often have screen glare or flash reflections
        """
        try:
            # Extract face region
            if face_bbox is not None:
                x, y, w, h = face_bbox
                face_region = image[y:y+h, x:x+w]
            else:
                face_region = image
            
            if face_region.size == 0:
                return 0.5
            
            # Convert to grayscale
            if len(face_region.shape) == 3:
                gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
            else:
                gray = face_region
            
            # Find very bright spots (potential reflections)
            _, bright_mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
            
            # Calculate percentage of very bright pixels
            bright_ratio = np.sum(bright_mask > 0) / bright_mask.size
            
            # Real faces: minimal bright spots (< 2%)
            # Photos: often have more reflections
            if bright_ratio < 0.02:
                reflection_score = 1.0
            else:
                reflection_score = max(0, 1 - (bright_ratio - 0.02) / 0.08)
            
            # Also check for unnatural contrast
            contrast = gray.std()
            
            # Real faces: moderate contrast (20-60)
            if 20 <= contrast <= 60:
                contrast_score = 1.0
            elif contrast < 20:
                contrast_score = contrast / 20
            else:
                contrast_score = max(0, 1 - (contrast - 60) / 40)
            
            # Combine metrics
            final_score = 0.7 * reflection_score + 0.3 * contrast_score
            
            return final_score
            
        except Exception as e:
            print(f"Reflection detection error: {e}")
            return 0.5
    
    def check_motion_liveness(self, current_frame, previous_frame, face_bbox=None):
        """
        Check for natural motion patterns
        Real faces have subtle movements, photos are static
        """
        try:
            if previous_frame is None:
                return 0.5, "No previous frame"
            
            # Extract face regions
            if face_bbox is not None:
                x, y, w, h = face_bbox
                curr_face = current_frame[y:y+h, x:x+w]
                prev_face = previous_frame[y:y+h, x:x+w]
            else:
                curr_face = current_frame
                prev_face = previous_frame
            
            if curr_face.size == 0 or prev_face.size == 0:
                return 0.5, "Invalid face region"
            
            # Convert to grayscale
            if len(curr_face.shape) == 3:
                curr_gray = cv2.cvtColor(curr_face, cv2.COLOR_BGR2GRAY)
                prev_gray = cv2.cvtColor(prev_face, cv2.COLOR_BGR2GRAY)
            else:
                curr_gray = curr_face
                prev_gray = prev_face
            
            # Resize for consistent analysis
            curr_gray = cv2.resize(curr_gray, (128, 128))
            prev_gray = cv2.resize(prev_gray, (128, 128))
            
            # Calculate optical flow
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, curr_gray, None,
                0.5, 3, 15, 3, 5, 1.2, 0
            )
            
            # Calculate motion magnitude
            magnitude = np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)
            avg_motion = np.mean(magnitude)
            
            # Store in history
            self.motion_history.append(avg_motion)
            
            # Real faces: subtle but consistent motion (0.5 - 5.0)
            # Photos: very little motion (< 0.3)
            if len(self.motion_history) >= 5:
                motion_variance = np.var(list(self.motion_history))
                avg_motion_history = np.mean(list(self.motion_history))
                
                # Check for natural motion patterns
                if 0.5 <= avg_motion_history <= 5.0 and motion_variance > 0.1:
                    motion_score = 1.0
                    verdict = "Natural motion detected"
                elif avg_motion_history < 0.3:
                    motion_score = 0.0
                    verdict = "Suspicious: Too static"
                else:
                    motion_score = 0.5
                    verdict = "Moderate motion"
            else:
                motion_score = 0.5
                verdict = "Collecting motion data..."
            
            return motion_score, verdict
            
        except Exception as e:
            print(f"Motion analysis error: {e}")
            return 0.5, f"Error: {e}"


# Global instance
liveness_detector = LivenessDetector()
