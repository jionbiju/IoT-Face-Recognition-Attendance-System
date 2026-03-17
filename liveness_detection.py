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
        
        # 6. Phone Screen Detection (new - specifically for phone photo spoofing)
        phone_screen_score = self.detect_phone_screen(image, face_bbox)
        scores['phone_screen'] = phone_screen_score
        
        # Calculate weighted overall score
        weights = {
            'texture': 0.30,      # Reduced slightly
            'color': 0.20,        # Reduced
            'frequency': 0.20,    # Increased - important for screen detection
            'quality': 0.10,      # Same
            'reflection': 0.10,   # Same
            'phone_screen': 0.10  # New - specific phone detection
        }
        
        # Enhanced anti-spoofing logic specifically for phone photos
        # Multiple indicators that suggest phone screen spoofing:
        phone_spoof_indicators = 0
        
        # 1. Low texture + high frequency = phone screen with Moiré
        if scores['texture'] < 0.5 and scores['frequency'] < 0.4:
            phone_spoof_indicators += 1
        
        # 2. Poor color distribution + screen artifacts
        if scores['color'] < 0.4 and scores['phone_screen'] < 0.5:
            phone_spoof_indicators += 1
        
        # 3. Unnatural reflections + screen characteristics
        if scores['reflection'] < 0.5 and scores['phone_screen'] < 0.6:
            phone_spoof_indicators += 1
        
        # 4. Multiple moderate failures (cumulative effect)
        moderate_failures = sum(1 for score in scores.values() if score < 0.6)
        if moderate_failures >= 4:
            phone_spoof_indicators += 1
        
        # Reject if multiple phone spoof indicators are present
        obvious_spoof = phone_spoof_indicators >= 2
        
        is_live = not obvious_spoof
        overall_score = sum(scores[k] * weights[k] for k in weights.keys())
        
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
        Analyze frequency domain for Moiré patterns and screen artifacts
        Photos of screens show characteristic patterns
        Enhanced for phone screen detection
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
            
            # Enhanced phone screen detection
            rows, cols = magnitude.shape
            center_row, center_col = rows // 2, cols // 2
            
            # 1. Check for regular grid patterns (phone pixels)
            # Look for periodic peaks in frequency domain
            freq_peaks = []
            for r in range(10, min(rows//2, 40)):  # Check various frequencies
                for c in range(10, min(cols//2, 40)):
                    if magnitude[center_row + r, center_col + c] > np.mean(magnitude) * 3:
                        freq_peaks.append((r, c, magnitude[center_row + r, center_col + c]))
            
            # Phone screens often have regular patterns
            regular_pattern_score = len(freq_peaks) / 20.0  # Normalize
            
            # 2. Check for Moiré patterns (interference between camera and screen)
            # Create ring masks for different frequency bands
            y, x = np.ogrid[:rows, :cols]
            
            # High frequency ring (Moiré patterns appear here)
            high_freq_mask = ((x - center_col)**2 + (y - center_row)**2) > (min(rows, cols) // 3)**2
            high_freq_mask &= ((x - center_col)**2 + (y - center_row)**2) < (min(rows, cols) // 2)**2
            
            # Mid frequency ring (natural face textures)
            mid_freq_mask = ((x - center_col)**2 + (y - center_row)**2) > (min(rows, cols) // 6)**2
            mid_freq_mask &= ((x - center_col)**2 + (y - center_row)**2) < (min(rows, cols) // 3)**2
            
            high_freq_energy = np.sum(magnitude[high_freq_mask])
            mid_freq_energy = np.sum(magnitude[mid_freq_mask])
            total_energy = np.sum(magnitude)
            
            high_freq_ratio = high_freq_energy / (total_energy + 1e-7)
            mid_freq_ratio = mid_freq_energy / (total_energy + 1e-7)
            
            # 3. Detect screen refresh patterns
            # Phones often show horizontal or vertical lines
            horizontal_lines = np.sum(magnitude[center_row-2:center_row+3, :])
            vertical_lines = np.sum(magnitude[:, center_col-2:center_col+3])
            line_energy = (horizontal_lines + vertical_lines) / (2 * total_energy + 1e-7)
            
            # Scoring logic for phone detection
            phone_indicators = 0
            
            # Too many regular frequency peaks = phone screen
            if regular_pattern_score > 0.3:
                phone_indicators += 1
            
            # Excessive high frequency = Moiré from screen
            if high_freq_ratio > 0.4:
                phone_indicators += 1
            
            # Strong line patterns = screen refresh
            if line_energy > 0.15:
                phone_indicators += 1
            
            # Unnatural frequency distribution
            if high_freq_ratio > mid_freq_ratio * 1.5:
                phone_indicators += 1
            
            # Calculate final score (lower = more likely phone)
            if phone_indicators >= 3:
                frequency_score = 0.1  # Very likely phone
            elif phone_indicators >= 2:
                frequency_score = 0.3  # Likely phone
            elif phone_indicators >= 1:
                frequency_score = 0.6  # Possibly phone
            else:
                # Natural face - check if frequency distribution is reasonable
                if 0.15 <= high_freq_ratio <= 0.35 and mid_freq_ratio > 0.1:
                    frequency_score = 1.0
                else:
                    frequency_score = 0.7
            
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
        Detect unnatural reflections/glare and screen characteristics
        Enhanced for phone screen detection
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
            
            # Convert to grayscale and HSV
            if len(face_region.shape) == 3:
                gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
                hsv = cv2.cvtColor(face_region, cv2.COLOR_BGR2HSV)
            else:
                gray = face_region
                hsv = None
            
            # 1. Detect screen glare/reflections
            _, bright_mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
            bright_ratio = np.sum(bright_mask > 0) / bright_mask.size
            
            # 2. Check for uniform illumination (phones often have even backlight)
            # Calculate illumination gradient
            grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
            
            # Real faces have natural lighting gradients
            # Phone screens have more uniform illumination
            avg_gradient = np.mean(gradient_magnitude)
            gradient_variance = np.var(gradient_magnitude)
            
            # 3. Check for screen-specific color characteristics
            screen_indicators = 0
            
            if hsv is not None:
                # Check saturation - phone screens often have oversaturated colors
                saturation = hsv[:, :, 1]
                avg_saturation = np.mean(saturation)
                
                # Check for blue light emission (common in phone screens)
                blue_channel = face_region[:, :, 0]  # BGR format
                green_channel = face_region[:, :, 1]
                red_channel = face_region[:, :, 2]
                
                blue_dominance = np.mean(blue_channel) / (np.mean(red_channel) + 1e-7)
                
                # Phone screens often have blue-shifted white balance
                if blue_dominance > 1.1:
                    screen_indicators += 1
                
                # Oversaturated colors
                if avg_saturation > 120:
                    screen_indicators += 1
            
            # 4. Check for pixelation artifacts
            # Resize down and up to detect pixelation
            small = cv2.resize(gray, (32, 32))
            enlarged = cv2.resize(small, gray.shape[::-1])
            pixelation_diff = np.mean(np.abs(gray.astype(float) - enlarged.astype(float)))
            
            # 5. Check for screen door effect (visible pixel grid)
            # Apply high-pass filter to detect regular patterns
            kernel = np.array([[-1, -1, -1], [-1, 8, -1], [-1, -1, -1]])
            filtered = cv2.filter2D(gray, -1, kernel)
            pattern_strength = np.std(filtered)
            
            # Scoring
            reflection_score = 1.0
            
            # Too many bright spots = screen glare
            if bright_ratio > 0.05:
                reflection_score -= 0.3
            
            # Too uniform illumination = screen backlight
            if avg_gradient < 15 and gradient_variance < 100:
                reflection_score -= 0.3
            
            # Screen color characteristics
            if screen_indicators >= 2:
                reflection_score -= 0.4
            elif screen_indicators >= 1:
                reflection_score -= 0.2
            
            # Pixelation artifacts
            if pixelation_diff > 10:
                reflection_score -= 0.2
            
            # Strong regular patterns = pixel grid
            if pattern_strength > 25:
                reflection_score -= 0.2
            
            # Ensure score is in valid range
            reflection_score = max(0.0, min(1.0, reflection_score))
            
            return reflection_score
            
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
    
    def detect_phone_screen(self, image, face_bbox=None):
        """
        Specific detection for phone screen characteristics
        Focuses on identifying photos displayed on phone screens
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
            if len(face_region.shape) == 3:
                gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
                lab = cv2.cvtColor(face_region, cv2.COLOR_BGR2LAB)
                hsv = cv2.cvtColor(face_region, cv2.COLOR_BGR2HSV)
            else:
                gray = face_region
                lab = None
                hsv = None
            
            phone_indicators = 0
            
            # 1. Check for LCD/OLED screen characteristics
            if lab is not None:
                # Check L*a*b* color space for unnatural color reproduction
                l_channel = lab[:, :, 0]  # Lightness
                a_channel = lab[:, :, 1]  # Green-Red
                b_channel = lab[:, :, 2]  # Blue-Yellow
                
                # Phone screens often have exaggerated color reproduction
                a_variance = np.var(a_channel)
                b_variance = np.var(b_channel)
                
                # Unnatural color variance indicates screen
                if a_variance > 400 or b_variance > 400:
                    phone_indicators += 1
            
            # 2. Check for screen refresh artifacts
            # Horizontal line detection (common in phone screens)
            horizontal_kernel = np.array([[-1, -1, -1], [2, 2, 2], [-1, -1, -1]])
            horizontal_edges = cv2.filter2D(gray, -1, horizontal_kernel)
            horizontal_strength = np.mean(np.abs(horizontal_edges))
            
            if horizontal_strength > 8:
                phone_indicators += 1
            
            # 3. Check for pixel grid patterns
            # Resize to detect regular pixel patterns
            resized = cv2.resize(gray, (64, 64))
            enlarged = cv2.resize(resized, gray.shape[::-1])
            
            # Calculate difference to detect pixelation
            pixel_diff = np.mean(np.abs(gray.astype(float) - enlarged.astype(float)))
            
            if pixel_diff > 12:
                phone_indicators += 1
            
            # 4. Check for backlight uniformity
            # Phone screens have very uniform backlighting
            # Calculate local standard deviation
            kernel_size = max(5, min(gray.shape) // 10)
            if kernel_size % 2 == 0:
                kernel_size += 1
            
            # Apply Gaussian blur and compare with original
            blurred = cv2.GaussianBlur(gray, (kernel_size, kernel_size), 0)
            local_variance = np.var(gray.astype(float) - blurred.astype(float))
            
            # Very low local variance = uniform backlight = screen
            if local_variance < 50:
                phone_indicators += 1
            
            # 5. Check for digital compression artifacts
            # Phone photos often have JPEG compression
            # Look for 8x8 block artifacts
            h, w = gray.shape
            block_artifacts = 0
            
            for i in range(8, h-8, 8):
                for j in range(8, w-8, 8):
                    # Check for discontinuities at block boundaries
                    vertical_diff = abs(int(gray[i, j]) - int(gray[i-1, j]))
                    horizontal_diff = abs(int(gray[i, j]) - int(gray[i, j-1]))
                    
                    if vertical_diff > 10 or horizontal_diff > 10:
                        block_artifacts += 1
            
            block_ratio = block_artifacts / ((h//8) * (w//8))
            if block_ratio > 0.1:
                phone_indicators += 1
            
            # 6. Check for screen door effect (visible subpixels)
            # Apply edge detection to find regular patterns
            edges = cv2.Canny(gray, 30, 100)
            
            # Count edge pixels in regular grid positions
            grid_edges = 0
            total_positions = 0
            
            for i in range(2, h-2, 3):  # Check every 3 pixels (typical subpixel spacing)
                for j in range(2, w-2, 3):
                    total_positions += 1
                    if edges[i, j] > 0:
                        grid_edges += 1
            
            if total_positions > 0:
                grid_ratio = grid_edges / total_positions
                if grid_ratio > 0.05:  # Too many edges in grid pattern
                    phone_indicators += 1
            
            # Calculate final score
            # More indicators = lower score (more likely phone screen)
            max_indicators = 6
            phone_screen_score = max(0.0, 1.0 - (phone_indicators / max_indicators))
            
            return phone_screen_score
            
        except Exception as e:
            print(f"Phone screen detection error: {e}")
            return 0.5


# Global instance
liveness_detector = LivenessDetector()
