"""Problem5.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1c2TU0YMkBon1ExkymoLbdiFhlVyoXoyD
"""

!pip install ultralytics transformers
from ultralytics import YOLO
import numpy as np
import os
from PIL import Image
import cv2
import torch
from torchvision import transforms
from transformers import CLIPProcessor, CLIPModel

class InvalidPathError(Exception):
    """Custom exception for invalid paths."""
    pass

def load_yolov8_model(model_path):
    """
    Load a pretrained YOLOv8 model from the provided path.

    Args:
        model_path (str): Path to the YOLOv8 model file.

    Returns:
        YOLO: Pretrained YOLOv8 model.
    """
    try:
        return YOLO(model_path)
    except Exception as e:
        raise InvalidPathError(f"Model file '{model_path}' not found") from e

def run_inference(model, image_paths, save=False, conf=0.5):
    """
    Perform object detection inference on the provided images using the given YOLOv8 model.

    Args:
        model (YOLO): Pretrained YOLOv8 model.
        image_paths (list of str): List of paths to the input image files.
        save (bool): Whether to save the inference results or not.
        conf (float): Confidence threshold for detection.

    Returns:
        list: List of YOLOv8 detection results.
    """
    results = []
    for path in image_paths:
        try:
            results.extend(model(path, save=save, conf=conf))
        except Exception as e:
            print(f"Error processing image '{path}': {e}")
    return results

def get_clip_features(image_path, clip_processor, clip_model):
    """
    Extract CLIP features from the provided image using the given CLIP model.

    Args:
        image_path (str): Path to the input image.
        clip_processor: CLIPProcessor instance.
        clip_model: CLIPModel instance.

    Returns:
        torch.Tensor: Extracted CLIP features for the image.
    """
    image = Image.open(image_path)
    preprocess = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
    ])
    image_tensor = preprocess(image).unsqueeze(0)

    with torch.no_grad():
        inputs = clip_processor(text=None, images=image_tensor, return_tensors="pt")
        image_features = clip_model.get_image_features(**inputs)

    return image_features


def main():
    model_path = 'yolov8m.pt'
    images_directory = 'All_Images'

    model = load_yolov8_model(model_path)

    image_files = [os.path.join(images_directory, f) for f in os.listdir(images_directory) if os.path.isfile(os.path.join(images_directory, f))]

    image_paths = [f for f in image_files if f.lower().endswith(('.jpg', '.jpeg'))]

    results = run_inference(model, image_paths)

    clip_device = "cuda" if torch.cuda.is_available() else "cpu"

    clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch16")
    clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch16")

    combined_entity_to_images = {}  # Creating a dictionary to combine all paths with the same key
    processed_image_paths = set()   # Keeping track of processed image paths

    for result, image_path in zip(results, image_paths):
        if image_path in processed_image_paths:
            continue  # Skipping processing if the image has been processed before
        processed_image_paths.add(image_path)

        subfolder_name = os.path.splitext(os.path.basename(image_path))[0]
        subfolder_path = os.path.join(images_directory, subfolder_name)
        os.makedirs(subfolder_path, exist_ok=True)

        entity_to_images = {}  # Creating a dictionary to associate entity labels with their images

        for res in result:
            label = [res.names[int(box.cls)] for box in res.boxes]
            for l in label:
                if l not in entity_to_images:
                    entity_to_images[l] = []

                # Appending the image path to the entity's list of images
                if image_path not in entity_to_images[l]:
                    entity_to_images[l].append(image_path)

        image_features = get_clip_features(image_path, clip_processor, clip_model)

        # Updating the combined dictionary with the current entity_to_images
        for entity, entity_image_paths in entity_to_images.items():
            if entity not in combined_entity_to_images:
                combined_entity_to_images[entity] = []
            combined_entity_to_images[entity].extend(entity_image_paths * len(image_paths))  # Extending cyclically

            for entity, entity_image_paths in entity_to_images.items():
                # Skipping creating a folder for entities without similar images or if similar_images is empty
                if len(combined_entity_to_images.get(entity, [])) <= 1:
                    continue

                entity_folder = os.path.join(subfolder_path, entity)
                os.makedirs(entity_folder, exist_ok=True)

                # Maintaining a set to track processed image paths for this entity
                processed_images_for_entity = set()

                similar_images = []
                for other_entity, other_entity_image_paths in combined_entity_to_images.items():
                    if other_entity == entity:
                        for other_entity_image_path in other_entity_image_paths:
                            if other_entity_image_path != image_path and other_entity_image_path not in processed_images_for_entity:
                                other_image_features = get_clip_features(other_entity_image_path, clip_processor, clip_model)
                                similarity = torch.cosine_similarity(image_features, other_image_features, dim=-1).item()
                                similar_images.append((other_entity_image_path, similarity))
                                processed_images_for_entity.add(other_entity_image_path)  # Adding processed image to set

                similar_images.sort(key=lambda x: x[1], reverse=True)

                for i, (similar_image_path, _) in enumerate(similar_images):
                    if i >= 3:
                        break  # Stopping after saving top 3 similar images

                    similar_image = Image.open(similar_image_path)

                    print(f"similar_image_path : {similar_image_path}")

                    # Finding the labels for the current similar image
                    similar_labels = []
                    for res in results:
                        for box in res.boxes:
                            label = res.names[int(box.cls)]
                            if similar_image_path in combined_entity_to_images.get(label, []):
                                similar_labels.append(label)

                    # Calculating the bounding box that covers all similar labels
                    min_x, min_y, max_x, max_y = float('inf'), float('inf'), 0, 0
                    for res in results:
                        print(res.path)
                        for box in res.boxes:
                            for x_min, y_min, x_max, y_max in box.xyxy.tolist():
                                label = res.names[int(box.cls)]
                                if label in similar_labels:
                                    min_x = int(min(min_x, x_min))
                                    min_y = int(min(min_y, y_min))
                                    max_x = int(max(max_x, x_max))
                                    max_y = int(max(max_y, y_max))
                                    print(f"xmin: {x_min}, ymin {y_min} , x_max: {x_max}, y_max: {y_max}")

                    # Converting the PIL.Image to a NumPy array
                    similar_image_np = np.array(similar_image)

                    # Drawing the rectangle on a copy of the similar image
                    cropped_image = similar_image_np.copy()
                    cv2.rectangle(cropped_image, (min_x, min_y), (max_x, max_y), (0, 255, 0), 2)  # Adding color and thickness

                    # Converting the modified NumPy array back to a PIL.Image and save it
                    cropped_image_pil = Image.fromarray(cropped_image)
                    cropped_image_pil.save(os.path.join(entity_folder, f"top{i+1}-crop.jpeg"))

if __name__ == "__main__":

    main()
