import cv2
import os
import numpy as np

# -----------------------------
# SETTINGS
# -----------------------------

FACE_CASCADE_PATH = r"C:\Users\USER\Documents\SENTINEL X\python\haarcascade_frontalface_default.xml"

ALLOWED_FACES_PATH = r"C:\Users\USER\Documents\SENTINEL X\assets\images\allowed_faces"

MODEL_PATH = r"C:\Users\USER\Documents\SENTINEL X\python\face_model.yml"


# -----------------------------
# LOAD FACE DETECTOR
# -----------------------------

face_cascade = cv2.CascadeClassifier(FACE_CASCADE_PATH)

recognizer = cv2.face.LBPHFaceRecognizer_create()

faces = []
labels = []

people = []

# -----------------------------
# READ PEOPLE
# -----------------------------

for person in os.listdir(ALLOWED_FACES_PATH):

    person_path = os.path.join(ALLOWED_FACES_PATH, person)

    if not os.path.isdir(person_path):
        continue

    people.append(person)

    label = len(people) - 1

    print(f"Training: {person}")

    for filename in os.listdir(person_path):

        image_path = os.path.join(person_path, filename)

        image = cv2.imread(image_path)

        if image is None:
            continue

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        detected_faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.3,
            minNeighbors=5
        )

        for (x, y, w, h) in detected_faces:

            face = gray[y:y+h, x:x+w]

            faces.append(face)
            labels.append(label)


# -----------------------------
# TRAIN MODEL
# -----------------------------

if len(faces) == 0:
    print("ERROR: No faces were found.")
    exit()

recognizer.train(faces, np.array(labels))

recognizer.save(MODEL_PATH)

# Save names
with open(
    r"C:\Users\USER\Documents\SENTINEL X\people.txt",
    "w"
) as file:

    for person in people:
        file.write(person + "\n")


print()
print("Training complete.")
print("People trained:", people)
print("Model saved to:", MODEL_PATH)