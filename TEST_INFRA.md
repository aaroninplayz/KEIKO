# E2E Test Infra: Keiko Real-Time Interview Analyzer

## Test Philosophy
- **Opaque-box, requirement-driven**: The E2E tests evaluate the system via external interfaces (HTTP routes, WebSockets) and assert output schemas, score logic, and database state transitions.
- **Methodology**: Category-Partition + Boundary Value Analysis (BVA) + Pairwise Combinatorial Testing + Real-World Workload Testing.
- **Offline-Safe & Fast**: Heavy machine learning dependencies (MediaPipe, PyTorch, transformers, sentence-transformers, Whisper, OpenCV) are intercepted and mocked at the pre-import layer. Tests run fully local and execute in less than 2 seconds.

## Feature Inventory
| # | Feature | Source (requirement) | Tier 1 (Feature) | Tier 2 (Boundary) | Tier 3 (Cross) | Tier 4 (Workload) |
|---|---------|---------------------|:----------------:|:-----------------:|:--------------:|:-----------------:|
| 1 | Live Audio Capture & Speech-to-Text | ORIGINAL_REQUEST R1 | 5 | 5 | ✓ | ✓ |
| 2 | Voice & Speech Analysis Sensors | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ | ✓ |
| 3 | Facial Expression Analysis | ORIGINAL_REQUEST R3a | 5 | 5 | ✓ | ✓ |
| 4 | Composite Engagement Tracking | ORIGINAL_REQUEST R3b | 5 | 5 | ✓ | ✓ |
| 5 | Professional Presence & Reports | ORIGINAL_REQUEST R4 | 5 | 5 | ✓ | ✓ |
| 6 | Robustness & Exception Safety | ORIGINAL_REQUEST R5 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- **Test Runner**: Python standard `unittest` library.
- **Mocking Strategy**: Mocks `mediapipe`, `transformers`, `sentence_transformers`, `whisper`, `cv2`, and `torch` via `sys.modules` pre-import overrides to avoid neural model downloading and inference overhead.
- **FastAPI TestClient**: Emulates HTTP API requests and bi-directional WebSocket connections.
- **Directory Layout**:
  - `scratch/test_realtime_analyzer.py` — The 71 E2E tests suite.
  - `scratch/test_conversation_engine.py` — The 13 existing conversation engine tests.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Complete Nominal Interview | F1, F2, F3, F4, F5, F6 | High |
| 2 | Interrupted Session Recovery | F1, F5, F6 | Medium |
| 3 | Slow/Delayed Network Stream | F1, F3, F4, F6 | Medium |
| 4 | Multi-Client Concurrent Stream | F3, F4, F6 | High |
| 5 | Missing Models Bootstrap | F1, F3, F4, F6 | Medium |

## Coverage Thresholds
- **Tier 1**: ≥5 tests per feature (30 total)
- **Tier 2**: ≥5 tests per feature (30 total)
- **Tier 3**: pairwise coverage of major feature interactions (6 total)
- **Tier 4**: ≥5 realistic application scenarios (5 total)
