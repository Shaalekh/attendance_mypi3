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
