#!/usr/bin/env python3
"""
Camera Configuration System for Face Recognition Project
Supports DroidCam, laptop webcam, and other external cameras
"""
import cv2
import json
import os
from datetime import datetime

class CameraManager:
    def __init__(self):
        self.config_file = "camera_config.json"
        self.config = self.load_config()
        
    def load_config(self):
        """Load camera configuration"""
        default_config = {
            "active_camera": 0,
            "cameras": {
                "laptop_webcam": {"index": 0, "name": "Laptop Webcam", "type": "built-in"},
                "droidcam": {"index": 2, "name": "DroidCam (Phone)", "type": "external"},
                "external": {"index": 1, "name": "External Camera", "type": "external"}
            },
            "droidcam_settings": {
                "resolution": {"width": 1280, "height": 720},
                "fps": 30,
                "auto_focus": True,
                "quality": "high"
            },
            "last_updated": datetime.now().isoformat()
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                # Merge with defaults for any missing keys
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
            except Exception as e:
                print(f"Error loading config: {e}")
                return default_config
        else:
            self.save_config(default_config)
            return default_config
    
    def save_config(self, config=None):
        """Save camera configuration"""
        if config is None:
            config = self.config
        
        config["last_updated"] = datetime.now().isoformat()
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"✓ Camera configuration saved to {self.config_file}")
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def test_camera(self, camera_index, duration=3):
        """Test a specific camera"""
        print(f"Testing camera {camera_index}...")
        
        try:
            cap = cv2.VideoCapture(camera_index)
            
            if not cap.isOpened():
                return False, "Cannot open camera"
            
            # Set optimal settings for DroidCam
            if camera_index == self.config["cameras"]["droidcam"]["index"]:
                droidcam_settings = self.config["droidcam_settings"]
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, droidcam_settings["resolution"]["width"])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, droidcam_settings["resolution"]["height"])
                cap.set(cv2.CAP_PROP_FPS, droidcam_settings["fps"])
                cap.set(cv2.CAP_PROP_AUTOFOCUS, 1 if droidcam_settings["auto_focus"] else 0)
            
            ret, frame = cap.read()
            if not ret:
                cap.release()
                return False, "Cannot read frames"
            
            height, width = frame.shape[:2]
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            print(f"✓ Camera {camera_index}: {width}x{height} @ {fps} FPS")
            
            # Show preview
            print(f"Showing preview for {duration} seconds (press 'q' to skip)")
            
            start_time = cv2.getTickCount()
            while True:
                ret, frame = cap.read()
                if ret:
                    # Add overlay information
                    cv2.putText(frame, f"Camera {camera_index} - {width}x{height}", 
                              (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    cv2.putText(frame, f"FPS: {fps:.1f}", 
                              (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    cv2.putText(frame, "Press 'q' to continue", 
                              (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    
                    # Add camera type indicator
                    camera_type = "Unknown"
                    for cam_name, cam_info in self.config["cameras"].items():
                        if cam_info["index"] == camera_index:
                            camera_type = cam_info["name"]
                            break
                    
                    cv2.putText(frame, f"Type: {camera_type}", 
                              (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    cv2.imshow(f'Camera {camera_index} Test', frame)
                    
                    key = cv2.waitKey(1) & 0xFF
                    elapsed = (cv2.getTickCount() - start_time) / cv2.getTickFrequency()
                    
                    if key == ord('q') or elapsed > duration:
                        break
                else:
                    break
            
            cv2.destroyAllWindows()
            cap.release()
            
            return True, f"Camera working: {width}x{height} @ {fps} FPS"
            
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def configure_droidcam(self):
        """Interactive DroidCam configuration"""
        print("\n🎥 DroidCam Configuration")
        print("=" * 40)
        
        # Test different camera indices to find DroidCam
        print("Scanning for DroidCam...")
        
        droidcam_found = False
        for index in [1, 2, 3, 4]:
            success, message = self.test_camera(index, duration=2)
            if success:
                response = input(f"Is camera {index} your DroidCam? (y/n): ").lower()
                if response == 'y':
                    self.config["cameras"]["droidcam"]["index"] = index
                    self.config["active_camera"] = index
                    droidcam_found = True
                    print(f"✓ DroidCam configured to use camera index {index}")
                    break
        
        if not droidcam_found:
            print("❌ DroidCam not found. Please check:")
            print("1. DroidCam app is running on your phone")
            print("2. DroidCam client is running on your computer")
            print("3. Phone and computer are connected")
            return False
        
        # Configure DroidCam settings
        print("\n📱 DroidCam Settings:")
        
        # Resolution
        print("Available resolutions:")
        print("1. 640x480 (Standard)")
        print("2. 1280x720 (HD)")
        print("3. 1920x1080 (Full HD)")
        
        res_choice = input("Choose resolution (1-3, default 2): ").strip()
        
        resolutions = {
            "1": {"width": 640, "height": 480},
            "2": {"width": 1280, "height": 720},
            "3": {"width": 1920, "height": 1080}
        }
        
        if res_choice in resolutions:
            self.config["droidcam_settings"]["resolution"] = resolutions[res_choice]
        
        # FPS
        fps_choice = input("Enter FPS (default 30): ").strip()
        if fps_choice.isdigit():
            self.config["droidcam_settings"]["fps"] = int(fps_choice)
        
        self.save_config()
        return True
    
    def get_active_camera(self):
        """Get the currently active camera index"""
        return self.config["active_camera"]
    
    def set_active_camera(self, camera_name):
        """Set active camera by name"""
        if camera_name in self.config["cameras"]:
            self.config["active_camera"] = self.config["cameras"][camera_name]["index"]
            self.save_config()
            return True
        return False
    
    def get_camera_info(self):
        """Get information about the active camera"""
        active_index = self.config["active_camera"]
        
        for name, info in self.config["cameras"].items():
            if info["index"] == active_index:
                return {
                    "name": info["name"],
                    "type": info["type"],
                    "index": active_index
                }
        
        return {"name": "Unknown", "type": "unknown", "index": active_index}

def main():
    """Interactive camera configuration"""
    print("🎥 Camera Configuration Tool")
    print("=" * 40)
    
    manager = CameraManager()
    
    while True:
        print("\nOptions:")
        print("1. Test all cameras")
        print("2. Configure DroidCam")
        print("3. Set active camera")
        print("4. Show current configuration")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ").strip()
        
        if choice == "1":
            print("\n🔍 Testing all cameras...")
            for i in range(5):
                success, message = manager.test_camera(i, duration=2)
                if success:
                    print(f"✓ Camera {i}: {message}")
                else:
                    print(f"❌ Camera {i}: {message}")
        
        elif choice == "2":
            manager.configure_droidcam()
        
        elif choice == "3":
            print("\nAvailable cameras:")
            for name, info in manager.config["cameras"].items():
                print(f"- {name}: {info['name']} (index {info['index']})")
            
            camera_name = input("Enter camera name (laptop_webcam/droidcam/external): ").strip()
            if manager.set_active_camera(camera_name):
                print(f"✓ Active camera set to {camera_name}")
            else:
                print("❌ Invalid camera name")
        
        elif choice == "4":
            print("\n📋 Current Configuration:")
            print(f"Active camera: {manager.get_active_camera()}")
            info = manager.get_camera_info()
            print(f"Camera name: {info['name']}")
            print(f"Camera type: {info['type']}")
            
            if info['type'] == 'external':
                droidcam_settings = manager.config["droidcam_settings"]
                print(f"DroidCam resolution: {droidcam_settings['resolution']['width']}x{droidcam_settings['resolution']['height']}")
                print(f"DroidCam FPS: {droidcam_settings['fps']}")
        
        elif choice == "5":
            print("👋 Goodbye!")
            break
        
        else:
            print("❌ Invalid choice")

if __name__ == "__main__":
    main()