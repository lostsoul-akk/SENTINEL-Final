# SENTINEL X Facial Recognition Module Documentation

## 1. Overview

The facial recognition system continuously monitors the connected camera and compares detected faces with the allowed faces stored in:

```text
assets/images/allowed_faces/
```

The facial recognition module consists primarily of:

```text
python/
├── train.py
├── camera.py
├── face_model.yml
├── people.txt
└── haarcascade_frontalface_default.xml
```

---

## 2. Input

### Allowed faces

Images of familiar or authorised people are stored in:

```text
assets/images/allowed_faces/
```

Each person should have a separate folder containing multiple images.

Example:

```text
allowed_faces/
├── Person_1/
│   ├── image1.jpg
│   └── image2.jpg
└── Person_2/
    ├── image1.jpg
    └── image2.jpg
```

### Camera input

`camera.py` receives a continuous live video feed from the webcam.

---

## 3. Training

`train.py` processes the images stored in `allowed_faces`.

The training process produces:

```text
python/face_model.yml
```

This is the trained facial recognition model.

It also creates:

```text
python/people.txt
```

This file links recognition labels to the names of the people in the allowed faces database.

---

## 4. Recognition Process

The live camera feed is continuously processed as follows:

```text
Camera Feed
     ↓
Face Detection
     ↓
Face Recognition
     ↓
Compare with Trained Faces
```

### Familiar face

If the detected face matches a person in the system:

```text
FACE_MATCH
access = 1
name = Recognised Person
```

### Unknown face

If the face does not match the allowed faces:

```text
UNKNOWN_FACE
access = 0
name = UNKNOWN
image_path = Saved Image Path
```

A photo of the unknown person is saved in:

```text
assets/images/detected_faces/
```

The system uses a cooldown period to prevent repeated alarms and duplicate image captures.

---

## 5. Expected Output

The facial recognition system produces two main outputs:

### Familiar Face

```text
event: FACE_MATCH
access: 1
name: Recognised Person
```

### Unknown Face

```text
event: UNKNOWN_FACE
access: 0
name: UNKNOWN
image_path: Path to captured image
```

---

## 6. Output Flow

```text
Camera
  ↓
Face Detection
  ↓
Face Recognition
  ↓
┌─────────────────┴──────────────────┐
│                                    │
FACE MATCH                      UNKNOWN FACE
│                                    │
access = 1                         access = 0
│                                    │
│                              Save Photo
│                                    │
└───────────────┐            ┌───────┘
                ↓            ↓
             Main Python System
                    ↓
              decision_engine.py
```

---

## 7. Use in Python Decision Making

The facial recognition system sends its output to the main SENTINEL X Python system.

The `decision_engine.py` should use the facial recognition result as an input for system decisions.

### If:

```text
FACE_MATCH
access = 1
```

The decision engine treats the person as familiar and continues with the appropriate system logic.

### If:

```text
UNKNOWN_FACE
access = 0
```

The decision engine receives the unknown-face event and initiates the defined threat analysis and response flow.

The facial recognition module does not perform threat analysis itself. Its responsibility is to:

```text
Detect
    ↓
Recognise
    ↓
Return 1 or 0
    ↓
Send Event
    ↓
Save Unknown Face Image
```

The main system and `decision_engine.py` are responsible for deciding the subsequent response.

---

## 8. Webcam Viewing

The camera continues facial recognition regardless of whether the live video is being viewed.

The system supports:

```text
view
```

to display the live webcam feed.

And:

```text
hide
```

to hide the webcam feed while facial recognition continues in the background.

The `quit` command stops the facial recognition system.
