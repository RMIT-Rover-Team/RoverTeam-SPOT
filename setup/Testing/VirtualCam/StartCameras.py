#!/usr/bin/env python3
import sys
from PIL import Image, ImageDraw, ImageFont
import time
import threading
import os
import numpy as np
import pyvirtualcam

CamFile = "EquinoxLoading.png"


def showImage(i):
    image = Image.open(CamFile).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size=200)
    draw.text((100,100), str(i), fill="white",font=font)

    frame = np.flip(np.array(image), axis=1)
    
    with pyvirtualcam.Camera(width=1920, height=1080, fps=5) as cam:
        print(f'Using virtual camera: {cam.device} id {i}')
        while True:
            cam.send(frame)
            cam.sleep_until_next_frame()

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: ", sys.argv[0], "<camera count>")
        exit()

    

    NoCams = int(sys.argv[1])
    print("Starting",NoCams,"Cameras")

    os.system("sudo modprobe v4l2loopback devices={NoCams}")

    threads = []
    for i in range(NoCams):
        print("Make",i)
        t = threading.Thread(target=showImage,args=(i,))
        t.start()
        threads.append(t)

    while True:
        time.sleep(1)
    
