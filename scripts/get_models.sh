#!/bin/sh
# Downloads the three ONNX models (about 40 MB) into models/.
set -e
cd "$(dirname "$0")/.." && mkdir -p models && cd models
[ -f face_detection_yunet_2023mar.onnx ] || curl -L -o face_detection_yunet_2023mar.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
[ -f face_recognition_sface_2021dec.onnx ] || curl -L -o face_recognition_sface_2021dec.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
[ -f MiniFASNetV2.onnx ] || curl -L -o MiniFASNetV2.onnx https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV2.onnx
[ -f MiniFASNetV1SE.onnx ] || curl -L -o MiniFASNetV1SE.onnx https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV1SE.onnx
[ -f antispoof_texture_q.onnx ] || curl -L -o antispoof_texture_q.onnx https://raw.githubusercontent.com/facenox/face-antispoof-onnx/main/models/best_model_quantized.onnx
ls -la
