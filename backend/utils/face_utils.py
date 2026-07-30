import cv2
import numpy as np
import mediapipe as mp
import base64
from io import BytesIO
from PIL import Image

class FaceUtils:
    def __init__(self):
        """Initialize MediaPipe face detection and mesh"""
        self.mp_face_detection = mp.solutions.face_detection
        self.mp_face_mesh = mp.solutions.face_mesh
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        
        # Initialize face detection
        self.face_detection = self.mp_face_detection.FaceDetection(
            model_selection=1,  # 1 for full range (0-5m), 0 for short range (0-2m)
            min_detection_confidence=0.5
        )
        
        # Initialize face mesh for landmarks
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,  # Refine landmarks around eyes and lips
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        print("✅ FaceUtils initialized successfully")
    
    def decode_base64_image(self, base64_string):
        """
        Decode base64 image to OpenCV format
        
        Args:
            base64_string: Base64 encoded image string
            
        Returns:
            numpy.ndarray: Decoded image in BGR format
        """
        try:
            # Remove data URL prefix if present
            if ',' in base64_string:
                base64_string = base64_string.split(',')[1]
            
            # Decode base64
            img_data = base64.b64decode(base64_string)
            nparr = np.frombuffer(img_data, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            return image, None
        except Exception as e:
            return None, f"Error decoding image: {str(e)}"
    
    def encode_image_to_base64(self, image, format='.jpg'):
        """
        Encode OpenCV image to base64
        
        Args:
            image: OpenCV image (numpy array)
            format: Image format ('.jpg' or '.png')
            
        Returns:
            str: Base64 encoded image
        """
        try:
            _, buffer = cv2.imencode(format, image)
            base64_str = base64.b64encode(buffer).decode('utf-8')
            return f"data:image/jpeg;base64,{base64_str}", None
        except Exception as e:
            return None, f"Error encoding image: {str(e)}"
    
    def detect_face(self, image):
        """
        Detect face in image and return bounding box
        
        Args:
            image: OpenCV image (numpy array)
            
        Returns:
            tuple: (x, y, width, height) of face bounding box
        """
        try:
            # Convert BGR to RGB
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Process image
            results = self.face_detection.process(rgb_image)
            
            if not results.detections:
                return None, "No face detected"
            
            # Get first detection
            detection = results.detections[0]
            bbox = detection.location_data.relative_bounding_box
            
            # Get image dimensions
            h, w, _ = image.shape
            
            # Calculate absolute coordinates
            x = int(bbox.xmin * w)
            y = int(bbox.ymin * h)
            width = int(bbox.width * w)
            height = int(bbox.height * h)
            
            # Ensure coordinates are within image bounds
            x = max(0, x)
            y = max(0, y)
            width = min(width, w - x)
            height = min(height, h - y)
            
            return (x, y, width, height), None
            
        except Exception as e:
            return None, f"Error detecting face: {str(e)}"
    
    def extract_face_landmarks(self, image):
        """
        Extract face landmarks using MediaPipe Face Mesh
        
        Args:
            image: OpenCV image (numpy array)
            
        Returns:
            list: Face landmarks coordinates
        """
        try:
            # Convert BGR to RGB
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Process image
            results = self.face_mesh.process(rgb_image)
            
            if not results.multi_face_landmarks:
                return None, "No face landmarks detected"
            
            # Get landmarks
            face_landmarks = results.multi_face_landmarks[0]
            
            # Extract landmarks as list of (x, y, z) coordinates
            landmarks = []
            for landmark in face_landmarks.landmark:
                landmarks.append({
                    'x': landmark.x,
                    'y': landmark.y,
                    'z': landmark.z
                })
            
            return landmarks, None
            
        except Exception as e:
            return None, f"Error extracting landmarks: {str(e)}"
    
    def draw_face_detection(self, image, bbox, landmarks=None):
        """
        Draw face detection visualization on image
        
        Args:
            image: OpenCV image
            bbox: Bounding box tuple (x, y, w, h)
            landmarks: Optional face landmarks
            
        Returns:
            numpy.ndarray: Image with drawings
        """
        try:
            img_copy = image.copy()
            
            # Draw bounding box
            x, y, w, h = bbox
            cv2.rectangle(img_copy, (x, y), (x + w, y + h), (0, 255, 0), 2)
            
            # Draw landmarks if provided
            if landmarks:
                h_img, w_img, _ = image.shape
                for point in landmarks:
                    px = int(point['x'] * w_img)
                    py = int(point['y'] * h_img)
                    cv2.circle(img_copy, (px, py), 2, (0, 255, 0), -1)
            
            return img_copy, None
            
        except Exception as e:
            return None, f"Error drawing detection: {str(e)}"
    
    def crop_face(self, image, bbox, margin=0.2):
        """
        Crop face from image with margin
        
        Args:
            image: OpenCV image
            bbox: Bounding box tuple (x, y, w, h)
            margin: Margin factor to add around face
            
        Returns:
            numpy.ndarray: Cropped face image
        """
        try:
            x, y, w, h = bbox
            h_img, w_img, _ = image.shape
            
            # Add margin
            margin_x = int(w * margin)
            margin_y = int(h * margin)
            
            # Calculate new coordinates with margin
            x1 = max(0, x - margin_x)
            y1 = max(0, y - margin_y)
            x2 = min(w_img, x + w + margin_x)
            y2 = min(h_img, y + h + margin_y)
            
            # Crop face
            face_crop = image[y1:y2, x1:x2]
            
            return face_crop, None
            
        except Exception as e:
            return None, f"Error cropping face: {str(e)}"
    
    def preprocess_face(self, face_image, target_size=(224, 224)):
        """
        Preprocess face image for model input
        
        Args:
            face_image: Cropped face image
            target_size: Target size for resizing
            
        Returns:
            numpy.ndarray: Preprocessed face image
        """
        try:
            # Resize
            resized = cv2.resize(face_image, target_size)
            
            # Convert to RGB (MediaPipe uses RGB)
            if len(resized.shape) == 3 and resized.shape[2] == 3:
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            else:
                rgb = cv2.cvtColor(resized, cv2.COLOR_GRAY2RGB)
            
            # Normalize to [0, 1]
            normalized = rgb.astype(np.float32) / 255.0
            
            return normalized, None
            
        except Exception as e:
            return None, f"Error preprocessing face: {str(e)}"
    
    def check_image_quality(self, image):
        """
        Check image quality for face recognition
        
        Args:
            image: OpenCV image
            
        Returns:
            dict: Quality metrics
        """
        try:
            metrics = {}
            
            # Check brightness
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            brightness = np.mean(gray)
            metrics['brightness'] = float(brightness)
            metrics['brightness_ok'] = 50 < brightness < 200
            
            # Check contrast (standard deviation)
            contrast = np.std(gray)
            metrics['contrast'] = float(contrast)
            metrics['contrast_ok'] = contrast > 30
            
            # Check sharpness (Laplacian variance)
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            sharpness = np.var(laplacian)
            metrics['sharpness'] = float(sharpness)
            metrics['sharpness_ok'] = sharpness > 100
            
            # Check image size
            h, w = image.shape[:2]
            metrics['width'] = w
            metrics['height'] = h
            metrics['size_ok'] = w >= 320 and h >= 240
            
            # Overall quality
            metrics['overall_ok'] = all([
                metrics['brightness_ok'],
                metrics['contrast_ok'],
                metrics['sharpness_ok'],
                metrics['size_ok']
            ])
            
            return metrics, None
            
        except Exception as e:
            return None, f"Error checking image quality: {str(e)}"
    
    def augment_face_image(self, face_image):
        """
        Apply data augmentation to face image
        
        Args:
            face_image: Face image
            
        Returns:
            list: Augmented images
        """
        augmented = []
        
        try:
            # Original
            augmented.append(face_image)
            
            # Horizontal flip
            flipped = cv2.flip(face_image, 1)
            augmented.append(flipped)
            
            # Small rotations
            h, w = face_image.shape[:2]
            center = (w // 2, h // 2)
            
            for angle in [-10, 10]:
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                rotated = cv2.warpAffine(face_image, M, (w, h))
                augmented.append(rotated)
            
            # Brightness adjustments
            for factor in [0.8, 1.2]:
                adjusted = cv2.convertScaleAbs(face_image, alpha=factor, beta=0)
                augmented.append(adjusted)
            
            return augmented, None
            
        except Exception as e:
            return None, f"Error augmenting face: {str(e)}"