# AudioBookGenerator
A audiobook generator made using the edge-tts library for python.
**Instructions**
It will use a intro video, a image and a final video, these videos must be inside a folder called video. (You can change the path if you want or add a button to it)
When you run it a interface will show up where you can select a .txt file or a folder for batch processing. You can use a default image in the video folder or use a custom image for the video.
Run it and wait, the processing will take around an hour for 10 hours for the video result. if you wan to use only the audio it will take 20~ minutes.
It uses a complex ffmpeg filter to concat the videos the image and the audio at the same time so its very fast. Previus versions took around 3~4 hours to render. 

