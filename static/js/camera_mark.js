// camera_mark.js
const startMarkBtn = document.getElementById("startMarkBtn");
const stopMarkBtn = document.getElementById("stopMarkBtn");
const cameraSelect = document.getElementById("cameraSelect");
const subjectSelect = document.getElementById("subjectSelect");
const periodSelect = document.getElementById("periodSelect");
const selectionStatus = document.getElementById("selectionStatus");
const markVideo = document.getElementById("markVideo");
const markStatus = document.getElementById("markStatus");
const recognizedList = document.getElementById("recognizedList");

let markStream = null;
let markInterval = null;
let recognizedIds = new Set();
let lastScanTime = 0;
let scanCounter = 0;
let activeCamera = 0; // Default camera
let availableDevices = [];
let selectedSubject = null; // {id, code, name}
let selectedPeriod = null; // period number

// Load subjects
async function loadSubjects() {
  try {
    const subjectsResponse = await fetch('/subjects');
    const subjectsData = await subjectsResponse.json();
    
    if (subjectsData.subjects && subjectsData.subjects.length > 0) {
      subjectsData.subjects.forEach(subject => {
        const option = document.createElement('option');
        option.value = subject.id;
        option.textContent = `${subject.code} - ${subject.name}`;
        option.dataset.code = subject.code;
        option.dataset.name = subject.name;
        subjectSelect.appendChild(option);
      });
    }
  } catch (error) {
    console.error('Error loading subjects:', error);
  }
}

// Update selection status
function updateSelectionStatus() {
  const hasSubject = subjectSelect.value !== '';
  const hasPeriod = periodSelect.value !== '';
  
  if (hasSubject && hasPeriod) {
    const subjectOption = subjectSelect.options[subjectSelect.selectedIndex];
    const periodOption = periodSelect.options[periodSelect.selectedIndex];
    
    selectionStatus.className = 'alert alert-success mb-0 py-2';
    selectionStatus.innerHTML = `
      <i class="fas fa-check-circle me-2"></i>
      <strong>Ready:</strong> ${subjectOption.textContent} - ${periodOption.textContent}
    `;
    startMarkBtn.disabled = false;
  } else {
    selectionStatus.className = 'alert alert-warning mb-0 py-2';
    selectionStatus.innerHTML = `
      <i class="fas fa-exclamation-triangle me-2"></i>
      Please select both subject and period to continue
    `;
    startMarkBtn.disabled = true;
  }
}

// Handle subject selection change
subjectSelect.addEventListener('change', function() {
  if (this.value) {
    const option = this.options[this.selectedIndex];
    selectedSubject = {
      id: parseInt(this.value),
      code: option.dataset.code,
      name: option.dataset.name
    };
    console.log('Subject selected:', selectedSubject);
  } else {
    selectedSubject = null;
  }
  updateSelectionStatus();
});

// Handle period selection change
periodSelect.addEventListener('change', function() {
  if (this.value) {
    selectedPeriod = parseInt(this.value);
    console.log('Period selected:', selectedPeriod);
  } else {
    selectedPeriod = null;
  }
  updateSelectionStatus();
});


async function loadCameraConfig() {
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
        } else {
          // Select DroidCam option (find it in the dropdown)
          const droidcamOption = Array.from(cameraSelect.options).find(option => 
            option.textContent.includes('DroidCam Video'));
          if (droidcamOption) {
            cameraSelect.value = droidcamOption.value;
            activeCamera = parseInt(droidcamOption.value);
          }
        }
        
        console.log(`Server configured camera: ${activeCamera}`);
      }
    } catch (error) {
      console.log('Using browser camera detection only');
      // Default to DroidCam if available, otherwise laptop camera
      if (cameraSelect.options.length > 1) {
        cameraSelect.value = cameraSelect.options[1].value; // DroidCam option
        activeCamera = parseInt(cameraSelect.options[1].value);
      }
    }
    
    // If no cameras found, show message
    if (availableDevices.length === 0) {
      cameraSelect.innerHTML = '<option value="">No cameras found</option>';
      startMarkBtn.disabled = true;
    }
    
  } catch (error) {
    console.error('Error loading cameras:', error);
    cameraSelect.innerHTML = '<option value="">Camera access denied</option>';
    startMarkBtn.disabled = true;
  }
}

// Handle camera selection change
cameraSelect.addEventListener('change', function() {
  const selectedIndex = parseInt(this.value);
  if (!isNaN(selectedIndex) && selectedIndex < availableDevices.length) {
    activeCamera = selectedIndex;
    console.log(`Camera selection changed to: ${selectedIndex}`);
    
    // If camera is currently running, restart with new camera
    if (markStream) {
      stopCamera();
      setTimeout(startCamera, 500); // Small delay to ensure cleanup
    }
  }
});

// Load camera config and subjects on page load
document.addEventListener('DOMContentLoaded', function() {
  loadCameraConfig();
  loadSubjects();
  updateSelectionStatus(); // Initial status check
});

async function startCamera() {
  startMarkBtn.disabled = true;
  stopMarkBtn.disabled = false;
  
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
      markStream = await navigator.mediaDevices.getUserMedia(constraints);
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
          
          markStream = await navigator.mediaDevices.getUserMedia(testConstraints);
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
    
    markVideo.srcObject = markStream;
    await markVideo.play();
    
    // Show camera info
    const track = markStream.getVideoTracks()[0];
    const settings = track.getSettings();
    const label = track.label || `Camera ${activeCamera}`;
    
    console.log(`Camera active: ${settings.width}x${settings.height} @ ${settings.frameRate}fps`);
    console.log(`Camera label: ${label}`);
    
    // Update status with actual camera info
    const cameraIcon = label.toLowerCase().includes('droidcam') ? '📱' : 
                      activeCamera === 0 ? '💻' : '📷';
    markStatus.innerText = `${cameraIcon} ${label} (${settings.width}x${settings.height}) - Scanning...`;
    markInterval = setInterval(captureAndRecognize, 800);
    
  } catch (err) {
    console.error('Camera error:', err);
    alert("Camera error: " + err.message + "\n\nTips:\n• Make sure DroidCam is running and connected\n• Check camera permissions\n• Try selecting a different camera from the dropdown");
    startMarkBtn.disabled = false;
    stopMarkBtn.disabled = true;
  }
}

function stopCamera() {
  if (markInterval) clearInterval(markInterval);
  if (markStream) markStream.getTracks().forEach(t => t.stop());
  startMarkBtn.disabled = false;
  stopMarkBtn.disabled = true;
  markStatus.innerText = "Stopped";
}

startMarkBtn.addEventListener("click", startCamera);
stopMarkBtn.addEventListener("click", stopCamera);

async function captureAndRecognize() {
  const currentTime = Date.now();
  
  // Add some natural variation to scanning frequency
  if (currentTime - lastScanTime < 600) {
    return; // Skip this scan to make it look more natural
  }
  
  lastScanTime = currentTime;
  scanCounter++;
  
  const canvas = document.createElement("canvas");
  canvas.width = markVideo.videoWidth || 640;
  canvas.height = markVideo.videoHeight || 480;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(markVideo, 0, 0, canvas.width, canvas.height);
  
  const blob = await new Promise(r => canvas.toBlob(r, "image/jpeg", 0.85));
  const fd = new FormData();
  fd.append("image", blob, "snap.jpg");
  
  // Add selected subject and period (both required)
  if (selectedSubject && selectedPeriod) {
    fd.append("subject_id", selectedSubject.id);
    fd.append("period", selectedPeriod);
  } else {
    // Should not happen as button is disabled, but handle gracefully
    markStatus.innerHTML = `<span class="text-warning">⚠️ Please select subject and period</span>`;
    return;
  }

  try {
    const res = await fetch("/recognize_face", { method: "POST", body: fd });
    const j = await res.json();

    if (j.recognized) {
      // Handle successful new attendance
      let statusText = `✅ Recognized: ${j.name} (${Math.round(j.confidence * 100)}%)`;
      
      // Add subject info if available
      if (j.subject) {
        statusText += ` | 📚 ${j.subject.code}`;
        if (j.subject.period) {
          statusText += ` (Period ${j.subject.period})`;
        }
      }
      
      // Add liveness score if available
      if (j.liveness_score) {
        statusText += ` | 🛡️ Live: ${Math.round(j.liveness_score * 100)}%`;
      }
      
      // Add advanced features info if available
      if (j.advanced_features) {
        const features = j.advanced_features;
        if (features.emotion) {
          statusText += ` | 😊 ${features.emotion}`;
        }
        if (features.estimated_age) {
          statusText += ` | 👤 ~${features.estimated_age}y`;
        }
      }
      
      markStatus.innerHTML = `<span class="text-success">${statusText}</span>`;

      // Only add to the visual list if not already showing in the current session
      if (!recognizedIds.has(j.student_id)) {
        recognizedIds.add(j.student_id);
        const li = document.createElement("li");
        li.className = "list-group-item d-flex justify-content-between align-items-center";
        
        let badgeText = new Date().toLocaleTimeString();
        if (j.advanced_features && j.advanced_features.emotion) {
          badgeText = `${j.advanced_features.emotion} | ${badgeText}`;
        }
        
        li.innerHTML = `
          <span><strong>${j.name}</strong></span>
          <span class="badge bg-primary rounded-pill">${badgeText}</span>
        `;
        recognizedList.prepend(li);
      }
    } else {
      // Handle errors including liveness check failures
      if (j.error && j.error.includes("Liveness check failed")) {
        // Show security warning for spoofing attempt
        markStatus.innerHTML = `<span class="text-danger"><i class="fas fa-shield-alt me-2"></i>⚠️ Security Alert: Photo/Video detected! Please use live camera.</span>`;
        
        // Show detailed liveness info in console for debugging
        if (j.liveness_details) {
          console.log("Liveness Detection Details:", j.liveness_details);
        }
      } else if (j.error && j.error.includes("Unknown person")) {
        const messages = [
          "Scanning...",
          "Analyzing face...",
          "Processing image...",
          "Detecting features...",
          "Matching patterns...",
          "Verifying identity..."
        ];
        const message = messages[scanCounter % messages.length];
        markStatus.innerHTML = `<span class="text-muted"><i class="spinner-border spinner-border-sm me-2"></i>${message} No match found</span>`;
      } else if (j.error && j.error.includes("Suspicious activity")) {
        markStatus.innerHTML = `<span class="text-danger"><i class="fas fa-exclamation-triangle me-2"></i>Security alert</span>`;
      } else {
        const messages = [
          "Scanning...",
          "Analyzing face...",
          "Processing image...",
          "Detecting features...",
          "Matching patterns...",
          "Verifying identity..."
        ];
        const message = messages[scanCounter % messages.length];
        markStatus.innerHTML = `<span class="text-muted"><i class="spinner-border spinner-border-sm me-2"></i>${message}</span>`;
      }
    }
  } catch (err) {
    console.error("Fetch error:", err);
    markStatus.innerHTML = `<span class="text-muted">📷 Camera ${activeCamera} - Scanning...</span>`;
  }
}
