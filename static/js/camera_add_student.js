// camera_add_student.js
const saveInfoBtn = document.getElementById("saveInfoBtn");
const startCaptureBtn = document.getElementById("startCaptureBtn");
const addStudentBtn = document.getElementById("addStudentBtn");
const cameraSelect = document.getElementById("cameraSelect");
const video = document.getElementById("video");
const captureStatus = document.getElementById("captureStatus");
const progressBar = document.getElementById("progressBar");

let student_id = null;
let captured = 0;
const maxImages = 50;
let images = [];
let stream = null;
let activeCamera = 0; // Default camera
let availableDevices = [];

// Load camera configuration and populate dropdown
async function loadCameraConfig() {
  const cameraInfo = document.getElementById('cameraInfo');
  
  try {
    // Get browser camera devices
    const devices = await navigator.mediaDevices.enumerateDevices();
    availableDevices = devices.filter(device => device.kind === 'videoinput');
    
    // Populate camera dropdown with only two main options
    cameraSelect.innerHTML = '';
    
    // Add Laptop Camera (always Camera 0)
    const laptopOption = document.createElement('option');
    laptopOption.value = 0;
    laptopOption.textContent = '💻 Laptop Camera';
    cameraSelect.appendChild(laptopOption);
    
    // Find and add DroidCam Video option
    let droidcamFound = false;
    availableDevices.forEach((device, index) => {
      const label = device.label || '';
      if (label.toLowerCase().includes('droidcam video') || 
          (label.toLowerCase().includes('droidcam') && label.toLowerCase().includes('video'))) {
        const droidcamOption = document.createElement('option');
        droidcamOption.value = index;
        droidcamOption.textContent = '📱 DroidCam Video';
        cameraSelect.appendChild(droidcamOption);
        droidcamFound = true;
      }
    });
    
    // If DroidCam Video not found by name, check Camera 2 (common DroidCam index)
    if (!droidcamFound && availableDevices.length > 2) {
      const droidcamOption = document.createElement('option');
      droidcamOption.value = 2;
      droidcamOption.textContent = '📱 DroidCam Video';
      cameraSelect.appendChild(droidcamOption);
    }
    
    // Try to get server camera configuration and select appropriate option
    try {
      const response = await fetch('/api/camera/current');
      const data = await response.json();
      if (data.camera_index !== undefined) {
        activeCamera = data.camera_index;
        
        // Select the appropriate option based on server config
        if (activeCamera === 0) {
          cameraSelect.value = 0;
          cameraInfo.innerHTML = `
            <i class="fas fa-camera me-2"></i>
            <span><strong>Active Camera:</strong> 💻 Laptop Camera (${data.resolution || 'Unknown resolution'})</span>
          `;
        } else {
          // Select DroidCam option (find it in the dropdown)
          const droidcamOption = Array.from(cameraSelect.options).find(option => 
            option.textContent.includes('DroidCam Video'));
          if (droidcamOption) {
            cameraSelect.value = droidcamOption.value;
            activeCamera = parseInt(droidcamOption.value);
            cameraInfo.innerHTML = `
              <i class="fas fa-camera me-2"></i>
              <span><strong>Active Camera:</strong> 📱 DroidCam Video (${data.resolution || 'Unknown resolution'})</span>
            `;
          }
        }
        
        cameraInfo.className = 'alert alert-success d-flex align-items-center';
        console.log(`Server configured camera: ${activeCamera}`);
      }
    } catch (error) {
      console.log('Using browser camera detection only');
      cameraInfo.innerHTML = `
        <i class="fas fa-exclamation-triangle me-2"></i>
        <span>Select your preferred camera below and save student info to begin.</span>
      `;
      cameraInfo.className = 'alert alert-warning d-flex align-items-center';
      
      // Default to DroidCam if available, otherwise laptop camera
      if (cameraSelect.options.length > 1) {
        cameraSelect.value = cameraSelect.options[1].value; // DroidCam option
        activeCamera = parseInt(cameraSelect.options[1].value);
      }
    }
    
    // If no cameras found, show message
    if (availableDevices.length === 0) {
      cameraSelect.innerHTML = '<option value="">No cameras found</option>';
      cameraInfo.innerHTML = `
        <i class="fas fa-exclamation-triangle me-2"></i>
        <span><strong>No cameras detected.</strong> Please check camera permissions and connections.</span>
      `;
      cameraInfo.className = 'alert alert-danger d-flex align-items-center';
    } else {
      cameraSelect.disabled = false; // Enable camera selection
      
      if (cameraInfo.className.includes('alert-info')) {
        cameraInfo.innerHTML = `
          <i class="fas fa-camera me-2"></i>
          <span><strong>2 camera options available.</strong> Select your preferred camera and save student info to begin.</span>
        `;
      }
    }
    
  } catch (error) {
    console.error('Error loading cameras:', error);
    cameraSelect.innerHTML = '<option value="">Camera access denied</option>';
    cameraInfo.innerHTML = `
      <i class="fas fa-ban me-2"></i>
      <span><strong>Camera access denied.</strong> Please allow camera permissions and refresh the page.</span>
    `;
    cameraInfo.className = 'alert alert-danger d-flex align-items-center';
  }
}

// Handle camera selection change
cameraSelect.addEventListener('change', function() {
  const selectedIndex = parseInt(this.value);
  if (!isNaN(selectedIndex) && selectedIndex < availableDevices.length) {
    activeCamera = selectedIndex;
    console.log(`Camera selection changed to: ${selectedIndex}`);
    
    // If camera is currently running, restart with new camera
    if (stream) {
      stopCamera();
      setTimeout(startCamera, 500); // Small delay to ensure cleanup
    }
  }
});

// Load camera config on page load
document.addEventListener('DOMContentLoaded', loadCameraConfig);

document.getElementById("studentForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const res = await fetch("/add_student", { method: "POST", body: fd });
  if (!res.ok) {
    alert("Failed to save student info");
    return;
  }
  const j = await res.json();
  student_id = j.student_id;
  alert("Student info saved. Select your camera and click Start Capture.");
  startCaptureBtn.disabled = false;
});

async function startCamera() {
  startCaptureBtn.disabled = true;
  
  try {
    console.log('Available cameras:', availableDevices);
    console.log('Selected camera index:', activeCamera);
    
    let constraints = {
      video: {
        width: { ideal: 1280, min: 640 },
        height: { ideal: 720, min: 480 },
        frameRate: { ideal: 30, min: 15 }
      }
    };
    
    // Use the selected camera device
    if (activeCamera >= 0 && activeCamera < availableDevices.length) {
      const selectedDevice = availableDevices[activeCamera];
      constraints.video.deviceId = { exact: selectedDevice.deviceId };
      console.log(`Using selected camera: ${selectedDevice.label || `Camera ${activeCamera}`}`);
    }
    
    try {
      stream = await navigator.mediaDevices.getUserMedia(constraints);
      console.log('✓ Successfully opened selected camera');
    } catch (error) {
      console.log('Selected camera failed, trying alternatives...', error);
      
      // Try each available camera until one works
      let cameraWorking = false;
      
      for (let i = availableDevices.length - 1; i >= 0; i--) {
        try {
          const testConstraints = {
            video: {
              deviceId: { exact: availableDevices[i].deviceId },
              width: { ideal: 1280, min: 640 },
              height: { ideal: 720, min: 480 }
            }
          };
          
          stream = await navigator.mediaDevices.getUserMedia(testConstraints);
          console.log(`✓ Using fallback camera ${i}: ${availableDevices[i].label}`);
          cameraSelect.value = i; // Update dropdown to reflect actual camera
          activeCamera = i;
          cameraWorking = true;
          break;
        } catch (e) {
          console.log(`Camera ${i} failed:`, e);
        }
      }
      
      if (!cameraWorking) {
        throw new Error('No cameras are accessible');
      }
    }
    
    video.srcObject = stream;
    await video.play();
    
    // Show camera info
    const track = stream.getVideoTracks()[0];
    const settings = track.getSettings();
    const label = track.label || `Camera ${activeCamera}`;
    
    console.log(`Camera active: ${settings.width}x${settings.height} @ ${settings.frameRate}fps`);
    console.log(`Camera label: ${label}`);
    
    // Update capture status with camera info
    const cameraIcon = label.toLowerCase().includes('droidcam') ? '📱' : 
                      activeCamera === 0 ? '💻' : '📷';
    captureStatus.innerText = `${cameraIcon} ${label} ready - Starting capture...`;
    
    // Start automatic capture
    captureImagesLoop();
    
  } catch (err) {
    console.error('Camera error:', err);
    alert("Camera error: " + err.message + "\n\nTips:\n• Make sure DroidCam is running and connected\n• Check camera permissions\n• Try selecting a different camera from the dropdown");
    startCaptureBtn.disabled = false;
  }
}

function stopCamera() {
  if (stream) {
    stream.getTracks().forEach(t => t.stop());
    stream = null;
  }
}

startCaptureBtn.addEventListener("click", startCamera);

async function captureImagesLoop() {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const ctx = canvas.getContext("2d");

  // Show which camera is being used
  const track = stream.getVideoTracks()[0];
  const label = track.label || `Camera ${activeCamera}`;
  const cameraIcon = label.toLowerCase().includes('droidcam') ? '📱' : 
                    activeCamera === 0 ? '💻' : '📷';

  while (captured < maxImages) {
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise(res => canvas.toBlob(res, "image/jpeg", 0.9));
    images.push(blob);
    captured++;
    
    captureStatus.innerText = `${cameraIcon} ${label} - Captured ${captured} / ${maxImages}`;
    progressBar.style.width = `${(captured / maxImages) * 100}%`;
    
    // Add visual feedback
    if (captured % 10 === 0) {
      progressBar.className = "progress-bar bg-info";
      setTimeout(() => progressBar.className = "progress-bar bg-success", 200);
    }
    
    // Small delay between captures
    await new Promise(r => setTimeout(r, 200));
  }

  captureStatus.innerText = `${cameraIcon} Capture complete! Uploading ${maxImages} images...`;
  progressBar.className = "progress-bar bg-warning";

  // Upload all images in one request
  const form = new FormData();
  form.append("student_id", student_id);
  images.forEach((b, i) => form.append("images[]", b, `img_${i}.jpg`));
  
  try {
    const resp = await fetch("/upload_face", { method: "POST", body: form });
    const result = await resp.json();
    
    if (resp.ok) {
      captureStatus.innerText = `✅ Upload complete! ${result.encodings_added || 0} faces processed automatically.`;
      progressBar.className = "progress-bar bg-success";
      alert(`Success! Captured and uploaded ${maxImages} images.\n${result.message || 'Images processed successfully.'}`);
      addStudentBtn.disabled = false;
    } else {
      throw new Error(result.error || 'Upload failed');
    }
  } catch (error) {
    captureStatus.innerText = `❌ Upload failed: ${error.message}`;
    progressBar.className = "progress-bar bg-danger";
    alert("Upload failed: " + error.message);
  }

  // Stop camera
  stopCamera();
}

addStudentBtn.addEventListener("click", () => {
  alert("Student registration complete! The system has been automatically trained with the new face data.");
  window.location.href = "/";
});
