"""
Fix Jion Recognition Issue
This script improves the face recognition model to better distinguish between students
"""
import os
import pickle
import numpy as np

def cosine_similarity_manual(a, b):
    """Calculate cosine similarity between two vectors"""
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    return dot_product / (norm_a * norm_b)

print("=" * 70)
print("FIXING JION RECOGNITION ISSUE")
print("=" * 70)

# Load current database
if not os.path.exists('face_encodings.pkl'):
    print("❌ No face_encodings.pkl found! Please train the model first.")
    exit(1)

with open('face_encodings.pkl', 'rb') as f:
    data = pickle.load(f)

if not isinstance(data, dict) or 'face_database' not in data:
    print("❌ Invalid database format!")
    exit(1)

face_db = data['face_database']
print(f"\n✓ Loaded database with {len(face_db)} students")

# Analyze and optimize encodings for each student
print("\n" + "-" * 70)
print("OPTIMIZING ENCODINGS:")
print("-" * 70)

optimized_db = {}

for student_id, encodings in face_db.items():
    print(f"\nStudent {student_id}:")
    print(f"  Original encodings: {len(encodings)}")
    
    if len(encodings) < 3:
        print(f"  ⚠️  Too few encodings, keeping all")
        optimized_db[student_id] = encodings
        continue
    
    # Convert to numpy arrays
    enc_arrays = [np.array(enc) for enc in encodings]
    
    # Calculate mean encoding
    mean_enc = np.mean(enc_arrays, axis=0)
    
    # Calculate similarities to mean
    similarities = []
    for enc in enc_arrays:
        sim = cosine_similarity_manual(enc, mean_enc)
        similarities.append(sim)
    
    # Keep only high-quality encodings (top 80% or above 0.95 similarity)
    threshold = max(0.95, np.percentile(similarities, 20))
    
    good_encodings = []
    for i, sim in enumerate(similarities):
        if sim >= threshold:
            good_encodings.append(encodings[i])
    
    # Ensure we keep at least 5 encodings
    if len(good_encodings) < 5 and len(encodings) >= 5:
        # Sort by similarity and keep top 5
        sorted_indices = np.argsort(similarities)[::-1][:5]
        good_encodings = [encodings[i] for i in sorted_indices]
    
    optimized_db[student_id] = good_encodings
    print(f"  Optimized encodings: {len(good_encodings)}")
    print(f"  Quality threshold: {threshold:.4f}")

# Save optimized database
data['face_database'] = optimized_db
data['version'] = '2.1'
data['optimized'] = True

with open('face_encodings.pkl', 'wb') as f:
    pickle.dump(data, f)

print("\n✓ Optimized database saved!")

# Verify cross-student similarities
print("\n" + "-" * 70)
print("VERIFICATION - CROSS-STUDENT SIMILARITIES:")
print("-" * 70)

student_ids = sorted(optimized_db.keys())
for i, sid1 in enumerate(student_ids):
    for sid2 in student_ids[i+1:]:
        enc1 = [np.array(e) for e in optimized_db[sid1]]
        enc2 = [np.array(e) for e in optimized_db[sid2]]
        
        max_sim = 0
        for e1 in enc1:
            for e2 in enc2:
                sim = cosine_similarity_manual(e1, e2)
                max_sim = max(max_sim, sim)
        
        print(f"Student {sid1} vs Student {sid2}: {max_sim:.4f}", end="")
        if max_sim > 0.80:
            print(" ⚠️  Still high")
        elif max_sim > 0.75:
            print(" ⚠️  Borderline")
        else:
            print(" ✓ Good")

print("\n" + "=" * 70)
print("OPTIMIZATION COMPLETE!")
print("=" * 70)
print("\nNext steps:")
print("1. Test recognition with: python test_jion_photo.py")
print("2. If still having issues, retrain with: python improve_recognition.py")
print("=" * 70)
