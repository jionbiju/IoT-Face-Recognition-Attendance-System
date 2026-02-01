// manage_students.js
let students = [];
let studentToDelete = null;

// Load students when page loads
document.addEventListener('DOMContentLoaded', loadStudents);

async function loadStudents() {
  try {
    const response = await fetch('/students');
    const data = await response.json();
    students = data.students;
    
    document.getElementById('loadingMsg').style.display = 'none';
    
    if (students.length === 0) {
      document.getElementById('noStudents').style.display = 'block';
    } else {
      document.getElementById('studentsContainer').style.display = 'block';
      renderStudentsTable();
    }
  } catch (error) {
    console.error('Error loading students:', error);
    document.getElementById('loadingMsg').innerHTML = '<p class="text-danger">Error loading students</p>';
  }
}

function renderStudentsTable() {
  const tbody = document.getElementById('studentsTable');
  tbody.innerHTML = '';
  
  students.forEach(student => {
    const row = document.createElement('tr');
    const createdDate = new Date(student.created_at).toLocaleDateString();
    
    row.innerHTML = `
      <td>${student.id}</td>
      <td><strong>${student.name}</strong></td>
      <td>${student.roll || '-'}</td>
      <td>${student.class || '-'}</td>
      <td>${student.section || '-'}</td>
      <td>${student.reg_no || '-'}</td>
      <td>${createdDate}</td>
      <td>
        <button class="btn btn-danger btn-sm" onclick="showDeleteModal(${student.id}, '${student.name}')">
          <i class="bi bi-trash"></i> Delete
        </button>
      </td>
    `;
    
    tbody.appendChild(row);
  });
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
  const originalText = deleteBtn.textContent;
  deleteBtn.textContent = 'Deleting...';
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
      
      // Show success message and reload to show reorganized IDs
      showAlert('Student deleted and IDs reorganized successfully!', 'success');
      
      // Reload students to show new IDs
      setTimeout(() => {
        loadStudents();
      }, 1000);
    } else {
      showAlert('Error deleting student', 'danger');
    }
  } catch (error) {
    console.error('Error deleting student:', error);
    showAlert('Error deleting student', 'danger');
  } finally {
    deleteBtn.textContent = originalText;
    deleteBtn.disabled = false;
    studentToDelete = null;
  }
});

// Handle reorganize IDs button
document.getElementById('reorganizeBtn').addEventListener('click', async () => {
  if (!confirm('This will reorganize all student IDs to be sequential (1, 2, 3...). Continue?')) {
    return;
  }
  
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