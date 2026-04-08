from ai.deepface_auth import verify_face_from_bytes
import sys

def main():
    try:
        with open('registered_face.jpg', 'rb') as f:
            data = f.read()
        res = verify_face_from_bytes(data)
        print("RESULT:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
