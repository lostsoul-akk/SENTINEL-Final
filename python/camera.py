import cv2
import os
import time
import threading
from datetime import datetime


# ============================================================
# SETTINGS
# ============================================================

FACE_CASCADE_PATH = r"C:\Users\USER\Documents\SENTINEL X\python\haarcascade_frontalface_default.xml"

MODEL_PATH = r"C:\Users\USER\Documents\SENTINEL X\python\face_model.yml"

PEOPLE_PATH = r"C:\Users\USER\Documents\SENTINEL X\people.txt"

SAVE_PATH = r"C:\Users\USER\Documents\SENTINEL X\assets\images\detected_faces"

CAMERA_NUMBER = 0

RECOGNITION_THRESHOLD = 70

PHOTO_COOLDOWN = 10


# ============================================================
# SYSTEM STATE
# ============================================================

view_webcam = False
running = True
last_unknown_time = 0
webcam_window_open = False


# ============================================================
# TERMINAL COMMAND LISTENER
# ============================================================

def command_listener():
    global view_webcam, running

    while running:

        try:
            command = input(
                "\nCommand (view / hide / quit): "
            ).strip().lower()

        except EOFError:
            break


        if command == "view":

            view_webcam = True

            print("[WEBCAM VIEW] ENABLED")


        elif command == "hide":

            view_webcam = False

            print("[WEBCAM VIEW] HIDDEN")
            print("[FACE RECOGNITION] STILL RUNNING")


        elif command == "quit":

            running = False

            print("[SYSTEM] STOPPING...")


        else:

            print(
                "Unknown command. Use: view, hide, or quit"
            )


# ============================================================
# SEND EVENT TO MAIN PYTHON
# ============================================================

def send_to_main(event, access, image_path=None, name=None):

    message = {
        "event": event,
        "access": access,
        "name": name,
        "image_path": image_path
    }

    # Temporary output
    # Later this is where information is sent to the main
    # SENTINEL X threat-analysis Python program.
    print("\nEVENT SENT TO MAIN:", message)


# ============================================================
# SETUP
# ============================================================

os.makedirs(SAVE_PATH, exist_ok=True)


face_cascade = cv2.CascadeClassifier(
    FACE_CASCADE_PATH
)

if face_cascade.empty():

    print("ERROR: Could not load Haar Cascade.")
    exit()


if not os.path.exists(MODEL_PATH):

    print("ERROR: face_model.yml was not found.")
    print("Run train.py first.")
    exit()


recognizer = cv2.face.LBPHFaceRecognizer_create()

recognizer.read(MODEL_PATH)


if not os.path.exists(PEOPLE_PATH):

    print("ERROR: people.txt was not found.")
    print("Run train.py first.")
    exit()


with open(PEOPLE_PATH, "r") as file:

    people = [
        line.strip()
        for line in file.readlines()
        if line.strip()
    ]


# ============================================================
# OPEN CAMERA
# ============================================================

webcam = cv2.VideoCapture(CAMERA_NUMBER)

if not webcam.isOpened():

    print("ERROR: Camera could not be opened.")
    exit()


# ============================================================
# START COMMAND THREAD
# ============================================================

command_thread = threading.Thread(
    target=command_listener,
    daemon=True
)

command_thread.start()


print("\n===================================")
print("SENTINEL X FACIAL RECOGNITION")
print("===================================")
print("Face recognition is running.")
print()
print("Terminal commands:")
print("view  - Show live webcam")
print("hide  - Hide webcam")
print("quit  - Stop system")
print("===================================")


# ============================================================
# MAIN CAMERA LOOP
# ============================================================

while running:

    success, img = webcam.read()

    if not success:

        print("ERROR: Camera could not be read.")
        break


    # ========================================================
    # FACE DETECTION
    # ========================================================

    gray = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2GRAY
    )

    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.3,
        minNeighbors=5,
        minSize=(60, 60)
    )


    # ========================================================
    # PROCESS DETECTED FACES
    # ========================================================

    for (x, y, w, h) in faces:

        # Extract detected face
        face = gray[y:y + h, x:x + w]


        # ====================================================
        # RECOGNIZE FACE
        # ====================================================

        label, confidence = recognizer.predict(face)


        # ====================================================
        # FAMILIAR FACE
        # ====================================================

        if confidence < RECOGNITION_THRESHOLD:

            access = 1

            if 0 <= label < len(people):

                name = people[label]

            else:

                name = "FAMILIAR"


            text = f"{name} | 1"

            box_color = (0, 255, 0)


            # Send information to main system
            # Only recognition information is sent.
            # Main Python decides what to do next.
            send_to_main(
                event="FACE_MATCH",
                access=1,
                name=name
            )


        # ====================================================
        # UNKNOWN FACE
        # ====================================================

        else:

            access = 0

            name = "UNKNOWN"

            text = "UNKNOWN | 0"

            box_color = (0, 0, 255)


            current_time = time.time()


            # =================================================
            # UNKNOWN FACE ALARM
            # =================================================

            if current_time - last_unknown_time >= PHOTO_COOLDOWN:

                timestamp = datetime.now().strftime(
                    "%Y-%m-%d_%H-%M-%S"
                )

                filename = (
                    f"UNKNOWN_{timestamp}.jpg"
                )

                filepath = os.path.join(
                    SAVE_PATH,
                    filename
                )


                # Save image
                cv2.imwrite(
                    filepath,
                    img
                )


                # Send alarm/event to main Python
                send_to_main(
                    event="UNKNOWN_FACE",
                    access=0,
                    image_path=filepath,
                    name="UNKNOWN"
                )


                print(
                    "\n[ALARM] UNKNOWN FACE DETECTED"
                )

                print(
                    f"Photo saved: {filepath}"
                )


                last_unknown_time = current_time


        # ====================================================
        # DRAW BOX
        # ====================================================

        cv2.rectangle(
            img,
            (x, y),
            (x + w, y + h),
            box_color,
            3
        )


        # ====================================================
        # DRAW RECOGNITION RESULT
        # ====================================================

        cv2.putText(
            img,
            text,
            (x, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            box_color,
            2
        )


    # ========================================================
    # SHOW WEBCAM ONLY WHEN COMMANDED
    # ========================================================

    if view_webcam:

        webcam_window_open = True


        cv2.putText(
            img,
            "LIVE SURVEILLANCE",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )


        cv2.imshow(
            "SENTINEL X SURVEILLANCE",
            img
        )


        # Keep OpenCV window responsive
        cv2.waitKey(1)


    # ========================================================
    # HIDE WEBCAM
    # ========================================================

    elif webcam_window_open:

        cv2.destroyWindow(
            "SENTINEL X SURVEILLANCE"
        )

        webcam_window_open = False


# ============================================================
# SHUTDOWN
# ============================================================

webcam.release()

cv2.destroyAllWindows()

print("\nSENTINEL X FACIAL RECOGNITION STOPPED")
