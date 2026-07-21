import base64
import numpy as np
import cv2
import asyncio
from modules.interview.orchestrator import InterviewOrchestrator

async def main():
    print("Initializing InterviewOrchestrator...")
    orchestrator = InterviewOrchestrator()
    
    # Create a blank black frame (640x480)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    _, buffer = cv2.imencode('.jpg', frame)
    frame_base64 = base64.b64encode(buffer).decode('utf-8')
    
    session_id = "test_session_123"
    
    # Create a mock websocket
    class MockWebSocket:
        async def accept(self): pass
        async def send_json(self, data): pass
        async def receive_json(self): return {}
    
    print("Connecting to orchestrator...")
    await orchestrator.connect(session_id, MockWebSocket())
    
    print("\n--- Processing Frame 1 (Throttle test, should return None) ---")
    res1 = await orchestrator.process_frame(session_id, frame_base64)
    print("Frame 1 response:", res1)
    
    print("\n--- Processing Frame 2 (Throttle test, should return None) ---")
    res2 = await orchestrator.process_frame(session_id, frame_base64)
    print("Frame 2 response:", res2)
    
    print("\n--- Processing Frame 3 (Throttle test, should process frame) ---")
    res3 = await orchestrator.process_frame(session_id, frame_base64)
    print("Frame 3 response keys:", list(res3.keys()) if res3 else None)
    if res3:
        print("Weighted overall score:", res3.get("weighted_overall"))
        print("Sensor results:")
        for sensor, data in res3["sensors"].items():
            print(f" - {sensor}: {data['score']} (details: {data['details']})")
            
    print("\n--- Weight Adjustment Test ---")
    # Change weights so confidence and eye contact have zero weight
    # and posture has full weight.
    new_weights = {
        "posture": 1.0,
        "eye_contact": 0.0,
        "attire": 0.0,
        "body_language": 0.0,
        "confidence": 0.0
    }
    print("Updating session weights to posture only...")
    orchestrator.update_weights(session_id, new_weights)
    
    print("Processing Frame 6 (to hit throttle cycle and get scores)...")
    await orchestrator.process_frame(session_id, frame_base64) # frame 4
    await orchestrator.process_frame(session_id, frame_base64) # frame 5
    res6 = await orchestrator.process_frame(session_id, frame_base64) # frame 6
    if res6:
        print("New Weighted overall score:", res6.get("weighted_overall"))
        print("Used weights in response:", res6.get("weights"))
        
    print("\nReleasing resources...")
    orchestrator.release_all()
    print("Test pipeline completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
