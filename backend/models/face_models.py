import numpy as np
import pickle
import cv2
from scipy.spatial.distance import cosine, euclidean
import mediapipe as mp

class FaceEmbeddingModel:
    """Model untuk menghasilkan embedding wajah menggunakan MediaPipe"""
    
    def __init__(self):
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5
        )
        self.embedding_size = 1404  # 468 landmarks * 3 coordinates (x, y, z)
        
    def generate_embedding(self, face_image):
        """
        Generate face embedding from face image
        
        Args:
            face_image: Cropped face image (RGB)
            
        Returns:
            numpy.ndarray: Face embedding vector
        """
        try:
            # Convert to RGB if needed
            if len(face_image.shape) == 3 and face_image.shape[2] == 3:
                rgb_image = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)
            else:
                rgb_image = face_image
            
            # Process with MediaPipe
            results = self.face_mesh.process(rgb_image)
            
            if not results.multi_face_landmarks:
                return None, "No face landmarks detected"
            
            # Get landmarks
            face_landmarks = results.multi_face_landmarks[0]
            
            # Extract landmarks as vector
            embedding = []
            for landmark in face_landmarks.landmark:
                embedding.extend([landmark.x, landmark.y, landmark.z])
            
            # Convert to numpy array
            embedding = np.array(embedding, dtype=np.float32)
            
            # Normalize embedding
            embedding_mean = np.mean(embedding)
            embedding_std = np.std(embedding)
            
            if embedding_std > 0:
                embedding = (embedding - embedding_mean) / embedding_std
            else:
                embedding = embedding - embedding_mean
            
            return embedding, None
            
        except Exception as e:
            return None, f"Error generating embedding: {str(e)}"
    
    def compare_embeddings(self, emb1, emb2, method='cosine'):
        """
        Compare two face embeddings
        
        Args:
            emb1: First embedding
            emb2: Second embedding
            method: Comparison method ('cosine' or 'euclidean')
            
        Returns:
            float: Similarity score (0-1 for cosine, distance for euclidean)
        """
        try:
            if method == 'cosine':
                # Cosine similarity
                similarity = 1 - cosine(emb1, emb2)
                return max(0, min(1, similarity))
            
            elif method == 'euclidean':
                # Euclidean distance (normalized)
                distance = euclidean(emb1, emb2)
                # Convert to similarity (0-1)
                similarity = 1 / (1 + distance)
                return similarity
            
            else:
                return 0
                
        except Exception as e:
            print(f"Error comparing embeddings: {e}")
            return 0


class FaceRecognitionModel:
    """Main face recognition model"""
    
    def __init__(self, threshold=0.5):
        self.embedding_model = FaceEmbeddingModel()
        self.threshold = threshold
        self.known_faces = []  # List of (embedding, metadata)
        
    def add_face(self, embedding, metadata):
        """Add known face to database"""
        self.known_faces.append((embedding, metadata))
        
    def recognize(self, query_embedding, top_k=1):
        """
        Recognize face from query embedding
        
        Args:
            query_embedding: Face embedding to recognize
            top_k: Number of top matches to return
            
        Returns:
            list: Top k matches with scores
        """
        if not self.known_faces:
            return []
        
        similarities = []
        
        for idx, (known_emb, metadata) in enumerate(self.known_faces):
            # Calculate similarity
            similarity = self.embedding_model.compare_embeddings(
                query_embedding, known_emb
            )
            similarities.append((similarity, idx, metadata))
        
        # Sort by similarity (descending)
        similarities.sort(reverse=True, key=lambda x: x[0])
        
        # Filter by threshold
        results = []
        for sim, idx, meta in similarities[:top_k]:
            if sim >= self.threshold:
                results.append({
                    'confidence': sim,
                    'metadata': meta,
                    'index': idx
                })
        
        return results
    
    def save_model(self, filepath):
        """Save model to file"""
        try:
            data = {
                'known_faces': self.known_faces,
                'threshold': self.threshold
            }
            with open(filepath, 'wb') as f:
                pickle.dump(data, f)
            return True, None
        except Exception as e:
            return False, str(e)
    
    def load_model(self, filepath):
        """Load model from file"""
        try:
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
            self.known_faces = data['known_faces']
            self.threshold = data['threshold']
            return True, None
        except Exception as e:
            return False, str(e)


class FaceQualityModel:
    """Model untuk mengecek kualitas wajah"""
    
    def __init__(self):
        self.face_detection = mp.solutions.face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=0.5
        )
        
    def assess_quality(self, image):
        """
        Assess face quality for recognition
        
        Returns:
            dict: Quality assessment results
        """
        try:
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = self.face_detection.process(rgb_image)
            
            if not results.detections:
                return {'valid': False, 'reason': 'No face detected'}
            
            detection = results.detections[0]
            
            # Check detection confidence
            confidence = detection.score[0]
            
            # Check face size relative to image
            h, w, _ = image.shape
            bbox = detection.location_data.relative_bounding_box
            face_area = (bbox.width * w) * (bbox.height * h)
            image_area = w * h
            face_ratio = face_area / image_area
            
            quality = {
                'valid': True,
                'detection_confidence': float(confidence),
                'face_ratio': float(face_ratio),
                'is_large_enough': face_ratio > 0.05,  # Face at least 5% of image
                'is_confident': confidence > 0.7
            }
            
            quality['overall_ok'] = quality['is_large_enough'] and quality['is_confident']
            
            return quality
            
        except Exception as e:
            return {'valid': False, 'error': str(e)}


class LivenessDetector:
    """Sederhana liveness detection untuk mencegah spoofing"""
    
    def __init__(self):
        self.blink_threshold = 0.2
        self.eye_aspect_ratio_threshold = 0.25
        
    def calculate_eye_aspect_ratio(self, eye_landmarks):
        """
        Calculate eye aspect ratio for blink detection
        """
        # Simplified calculation
        vertical_1 = np.linalg.norm(eye_landmarks[1] - eye_landmarks[5])
        vertical_2 = np.linalg.norm(eye_landmarks[2] - eye_landmarks[4])
        horizontal = np.linalg.norm(eye_landmarks[0] - eye_landmarks[3])
        
        ear = (vertical_1 + vertical_2) / (2.0 * horizontal)
        return ear
    
    def check_blink(self, landmarks_sequence):
        """
        Check if there's a blink in the sequence
        """
        # Simplified blink detection
        if len(landmarks_sequence) < 2:
            return False
        
        ears = []
        for landmarks in landmarks_sequence[-10:]:  # Check last 10 frames
            # Extract eye landmarks (simplified)
            left_eye = landmarks[33:42]  # Left eye indices
            right_eye = landmarks[362:371]  # Right eye indices
            
            left_ear = self.calculate_eye_aspect_ratio(left_eye)
            right_ear = self.calculate_eye_aspect_ratio(right_eye)
            ear = (left_ear + right_ear) / 2.0
            ears.append(ear)
        
        # Check for significant drop in EAR (blink)
        if len(ears) >= 5:
            avg_ear = np.mean(ears[:3])
            if avg_ear > self.eye_aspect_ratio_threshold:
                # Check for later frames with low EAR
                if min(ears[3:]) < self.eye_aspect_ratio_threshold * 0.8:
                    return True
        
        return False
    
    def detect_liveness(self, frame_sequence):
        """
        Detect if face is live (not a photo/video)
        
        Args:
            frame_sequence: List of face landmark sets over time
            
        Returns:
            dict: Liveness assessment
        """
        if len(frame_sequence) < 5:
            return {'live': False, 'confidence': 0, 'reason': 'Insufficient frames'}
        
        # Check for blink
        has_blink = self.check_blink(frame_sequence)
        
        # Check for micro-movements (simplified)
        movements = []
        for i in range(1, len(frame_sequence)):
            # Calculate movement of nose tip (landmark 1)
            prev_nose = frame_sequence[i-1][1]['z'] if i-1 < len(frame_sequence) else 0
            curr_nose = frame_sequence[i][1]['z'] if i < len(frame_sequence) else 0
            movements.append(abs(curr_nose - prev_nose))
        
        has_movement = np.mean(movements) > 0.01 if movements else False
        
        # Determine liveness
        live_score = 0
        if has_blink:
            live_score += 0.5
        if has_movement:
            live_score += 0.3
        
        is_live = live_score >= 0.5
        
        return {
            'live': is_live,
            'confidence': live_score,
            'has_blink': has_blink,
            'has_movement': has_movement,
            'frames_analyzed': len(frame_sequence)
        }