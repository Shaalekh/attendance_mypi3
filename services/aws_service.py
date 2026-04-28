import boto3
import cv2


class AWSService:
    def __init__(self):
        self.client = boto3.client("rekognition")
        self.collection_id = "attendance_collection"

    def recognize_face(self, frame):
        # Encode image to JPEG
        _, buffer = cv2.imencode(".jpg", frame)
        bytes_image = buffer.tobytes()

        response = self.client.search_faces_by_image(
            CollectionId=self.collection_id,
            Image={"Bytes": bytes_image},
            MaxFaces=1,
            FaceMatchThreshold=80
        )

        if response["FaceMatches"]:
            return response["FaceMatches"][0]["Face"]["ExternalImageId"]

        return None

    def index_face(self, frame, face_id: str):
        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            raise RuntimeError("Failed to encode image for AWS indexing")
        return self.index_face_bytes(buffer.tobytes(), face_id)

    def index_face_bytes(self, image_bytes: bytes, face_id: str):
        return self.client.index_faces(
            CollectionId=self.collection_id,
            Image={"Bytes": image_bytes},
            ExternalImageId=face_id,
            MaxFaces=1,
            DetectionAttributes=[],
        )

    def face_id_exists(self, face_id: str) -> bool:
        next_token = None
        while True:
            kwargs = {"CollectionId": self.collection_id, "MaxResults": 100}
            if next_token:
                kwargs["NextToken"] = next_token
            response = self.client.list_faces(**kwargs)
            for face in response.get("Faces", []):
                if face.get("ExternalImageId") == face_id:
                    return True
            next_token = response.get("NextToken")
            if not next_token:
                return False
