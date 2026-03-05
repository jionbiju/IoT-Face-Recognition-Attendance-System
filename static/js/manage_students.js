// manage_students.js
let students = [];
let studentToDelete = null;

// Load students when page loads
document.addEventListener('DOMContentLoaded', loadStudents);

async function loadStudents() {
  const loadingMsg = document.getElementById('loadingMsg');
  const studentsContainer = document.getElementById('studentsContainer');
  const noStudents = document.getElementById('noStudents');
  
  try {
    loadingMsg.style.display = 'block';
    studentsContainer.style.display = 'none';
    noStudents.style.display = 'none';
    
    const response = await fetch('/students');
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    
    if (data.error) {
      throw new Error(data.error);
    }
    
    students = data.students || [];
    
    loadingMsg.style.display = 'none';
    
    if (students.length === 0) {
      noStudents.style.display = 'block';
    } else {
      studentsContainer.style.display = 'block';
      renderStudentsTable();
    }
    
    console.log(`Loaded ${students.length} students successfully`);
    
  } catch (error) {
    console.error('Error loading students:', error);
    loadingMsg.innerHTML = `
      <div class="alert alert-danger">
        <i class="bi bi-exclamation-triangle-fill me-2"></i>
        <strong>Error loading students:</strong> ${error.message}
        <br><br>
        <button class="btn btn-sm btn-primary" onclick="location.reload()">
          <i class="bi bi-arrow-clockwise me-1"></i>Retry
        </button>
      </div>
    `;
  }
}

function renderStudentsTable() {
  const tbody = document.getElementById('studentsTable');
  tbody.innerHTML = '';
  
  if (!students || students.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No students found</td></tr>';
    return;
  }
  
  students.forEach(student => {
    const row = document.createElement('tr');
    
    // Safely handle date
    let createdDate = '-';
    try {
      if (student.created_at) {
        createdDate = new Date(student.created_at).toLocaleDateString();
      }
    } catch (e) {
      console.warn('Invalid date for student:', student.id);
    }
    
    // Escape student name for onclick
    const escapedName = (student.name || 'Unknown').replace(/'/g, "\\'");
    
    row.innerHTML = `
      <td>${student.id || '-'}</td>
      <td><strong>${student.name || 'Unknown'}</strong></td>
      <td>${student.roll || '-'}</td>
      <td>${student.class || '-'}</td>
      <td>${student.section || '-'}</td>
      <td>${student.reg_no || '-'}</td>
      <td>${createdDate}</td>
      <td>
        <button class="btn btn-danger btn-sm" onclick="showDeleteModal(${student.id}, '${escapedName}')">
          <i class="bi bi-trash"></i> Delete
        </button>
      </td>
    `;
    
    tbody.appendChild(row);
  });
  
  console.log(`Rendered ${students.length} students in table`);
}

function showDeleteModal(studentId, studentName) {
  studentToDelete = studentId;
  document.getElementById('deleteStudentName').textContent = studentName;
  const modal = new bootstrap.Modal(document.getElementById('deleteModal'));
  modal.show();
}

// Handle delete confirmation
document.getElementById('confirmDeleteBtn').addEventListener('click', async () => {
  if (!studentToDelete) return;
  
  const deleteBtn = document.getElementById('confirmDeleteBtn');
  const originalText = deleteBtn.innerHTML;
  deleteBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Deleting...';
  deleteBtn.disabled = true;
  
  try {
    const response = await fetch(`/students/${studentToDelete}`, {
      method: 'DELETE'
    });
    
    const result = await response.json();
    
    if (result.deleted) {
      // Remove student from local array
      students = students.filter(s => s.id !== studentToDelete);
      
      // Re-render table
      if (students.length === 0) {
        document.getElementById('studentsContainer').style.display = 'none';
        document.getElementById('noStudents').style.display = 'block';
      } else {
        renderStudentsTable();
      }
      
      // Close modal
      const modal = bootstrap.Modal.getInstance(document.getElementById('deleteModal'));
      modal.hide();
      
      // Show detailed success message
      const details = [
        `Student: ${result.student_name}`,
        `Images deleted: ${result.images_deleted}`,
        `Attendance records deleted: ${result.attendance_records_deleted}`,
        `Face encodings removed from model`
      ];
      
      showAlert(
        `<strong>Student Deleted Successfully!</strong><br>
        <small>${details.join(' | ')}</small>`, 
        'success'
      );
      
      // Reload students to show reorganized IDs
      setTimeout(() => {
        loadStudents();
      }, 2000);
    } else {
      showAlert(`Error: ${result.error || 'Failed to delete student'}`, 'danger');
    }
  } catch (error) {
    console.error('Error deleting student:', error);
    showAlert('Error deleting student. Please try again.', 'danger');
  } finally {
    deleteBtn.innerHTML = originalText;
    deleteBtn.disabled = false;
    studentToDelete = null;
  }
});

// Handle reorganize IDs button
document.getElementById('reorganizeBtn').addEventListener('click', async () => {
  if (!confirm('This will reorganize all student IDs to be sequential (1, 2, 3...). Continue?')) {
    return;
  }
  
  // DANGEROUS FUNCTION REMOVED - This was causing database corruption
  showAlert('ID reorganization has been disabled for safety. Student IDs remain stable.', 'warning');
  return;
  
  /*
  const reorganizeBtn = document.getElementById('reorganizeBtn');
  const originalText = reorganizeBtn.textContent;
  reorganizeBtn.textContent = 'Reorganizing...';
  reorganizeBtn.disabled = true;
  
  try {
    const response = await fetch('/reorganize_ids', {
      method: 'POST'
    });
    
    const result = await response.json();
    
    if (result.success) {
      showAlert('Student IDs reorganized successfully!', 'success');
      // Reload students to show new IDs
      setTimeout(() => {
        loadStudents();
      }, 1000);
    } else {
      showAlert(`Error: ${result.error}`, 'danger');
    }
  } catch (error) {
    console.error('Error reorganizing IDs:', error);
    showAlert('Error reorganizing student IDs', 'danger');
  } finally {
    reorganizeBtn.textContent = originalText;
    reorganizeBtn.disabled = false;
  }
  */
});

function showAlert(message, type) {
  const alertDiv = document.createElement('div');
  alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
  alertDiv.innerHTML = `
    ${message}
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  `;
  
  // Insert at top of container
  const container = document.querySelector('.container .card');
  container.insertBefore(alertDiv, container.firstChild);
  
  // Auto-dismiss after 5 seconds
  setTimeout(() => {
    if (alertDiv.parentNode) {
      alertDiv.remove();
    }
  }, 5000);
}