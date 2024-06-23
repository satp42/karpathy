from youtube_transcript_api import YouTubeTranscriptApi
import cv2
import numpy as np
from datetime import datetime, timedelta, time

import base64
import time
import openai  # Assuming 'openai' is the correct module for OpenAI API
from pytube import YouTube

# Set your OpenAI API key
api_key = ""
openai.api_key = api_key

video_id = "NorXFOobehY"

transcript = YouTubeTranscriptApi.get_transcript(video_id)

def download_video(video_id):
    print("Downloading video...")
    # check if video is already downloaded
    try:
        with open(f"videos/{video_id}.mp4", "r") as file:
            print("Video already downloaded.")
            return True, None
    except FileNotFoundError:
        print("Video not downloaded yet.")
        pass
    try: 
        yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
        stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').asc().first().download(filename="videos/{}.mp4".format(video_id))
        if stream:
            stream.download()
            return True, None
        else:
            return False
    except Exception as e:
        return False, str(e)

def format_time(seconds):
    delta = timedelta(seconds=seconds)
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    formatted_time = '{:02}:{:02}:{:02}'.format(hours, minutes, seconds)
    return formatted_time

def combine_transcript(transcript):
    combined_transcript = []
    current_interval_start = transcript[0]['start']
    current_interval_text = ""

    for item in transcript:
        if item['start'] - current_interval_start > 30:
            duration = item['start'] - current_interval_start
            combined_transcript.append({
                'text': current_interval_text.strip(),
                'start': format_time(current_interval_start),
                'end': format_time(current_interval_start + duration),
                'duration': format_time(duration)
            })
            current_interval_start = item['start']
            current_interval_text = ""

        current_interval_text += item['text'] + " "

    duration = transcript[-1]['start'] - current_interval_start
    combined_transcript.append({
        'text': current_interval_text.strip(),
        'start': format_time(current_interval_start),
        'end': format_time(current_interval_start + duration),
        'duration': format_time(duration)
    })

    return combined_transcript

loaded_object = combine_transcript(transcript)

def take_screenshot(video_path, output_path, timestamp):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error: Couldn't open the video file.")
        return
    
    for item in timestamp:
        cap.set(cv2.CAP_PROP_POS_MSEC, item * 1000)
        success, frame = cap.read()
        if not success:
            print("Error: Couldn't read frame at the specified timestamp.")
            return
        cv2.imwrite(output_path + f"{item}.jpeg", frame)
    
    cap.release()

def timestamp_to_seconds(timestamp):
    hours, minutes, seconds = map(int, timestamp.split(':'))
    total_seconds = hours * 3600 + minutes * 60 + seconds
    return total_seconds

download_video(video_id)

video_path = 'videos/{}.mp4'.format(video_id)
output_path = 'screenshots/'
timestamp_in_seconds = [timestamp_to_seconds(time['start']) for time in loaded_object]

take_screenshot(video_path, output_path, timestamp_in_seconds)

def compare_images(img1, img2, method="mse"):
    t0 = time.time()
    img1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY) if len(img1.shape) > 2 else img1
    img2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY) if len(img2.shape) > 2 else img2
    img1 = cv2.resize(img1, (img2.shape[1], img2.shape[0])) if img1.shape != img2.shape else img1
    img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0])) if img2.shape != img1.shape else img2

    if method == "mse":
        diff = np.square(img1 - img2).mean()
        print(f"Time taken: {time.time() - t0:.2f}s")
        return diff
    else:
        raise ValueError(f"Invalid comparison method: {method}")

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

n = 4
final_list = []

for i in range(0, len(loaded_object), n):
    combined_text = ''
    images = []
    prev = loaded_object[i-1]['text'] if i > 0 else ""
    start = loaded_object[i]['start']
    end = ''

    for j in range(n):
        if i + j < len(loaded_object):
            combined_text += " " + loaded_object[i + j]['text']
            end = loaded_object[i + j]['end']
            prev_image_path = f"screenshots/{timestamp_to_seconds(loaded_object[i + j - 1]['start'])}.jpeg"
            curr_image_path = f"screenshots/{timestamp_to_seconds(loaded_object[i + j]['start'])}.jpeg"
            
            prev_image = cv2.imread(prev_image_path)
            curr_image = cv2.imread(curr_image_path)

            if prev_image is None or curr_image is None:
                print(f"Warning: Could not read one of the images: {prev_image_path} or {curr_image_path}")
                continue

            if compare_images(prev_image, curr_image) >= 10:
                images.append(curr_image_path)

    final_list.append({'combined_text': combined_text, 'prev_sentence': prev, 'images': images, 'start': start, 'end': end})

def generate_prompt(current_text, previous_text, images):
    content = [
        {"type": "text", "text": f"""
        
        You will be given CURRENT TEXT of transcribed audio and the images from a youtube video.
        Your task is to curate a section of blog which should have the exact explanation of topics which are being discussed in the image and 
        in the CURRENT TEXT. 
        
        The images and the CURRENT TEXT may contain complex topic explanation. You have to break down
        complex topics into sub topics step-by-step and explain them in detail.
        If the CURRENT TEXT is not sufficient or cut off, you can take reference from the PREVIOUS TEXT.
        
        Write the blog section in first-person style.
        
        If codes are being explained you also need to include them in your answer.
        If some references are being made you can add them in Blockquotes (>)
        DO NOT include any conclusion in the output.
        DO NOT include your opinions in the final response.
        Apply heading level 3 (###) to the main topic and use lower-level headings such as (####) if there are any sub-topics.
        
        Your response should be as detailed as possible.

        You should output in markdown syntax
         
        The images are given to you in the following order. When attaching an image, make sure to use the correct filename in your markdown syntax:
        - {', '.join(["../{}".format(image) for image in images])}

        PREVIOUS TEXT: {previous_text}

        CURRENT TEXT: {current_text}
        """}
    ]
    
    for image in images:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encode_image(image)}"}})

    PROMPT_MESSAGES = [
        {
            "role": "user",
            "content": content,
        }
    ]
    
    return PROMPT_MESSAGES


def generate_answer(prompt):
    params = {
        "model": "gpt-4o",
        "messages": prompt,
        "max_tokens": 2000,
    }
    result = openai.ChatCompletion.create(**params)
    print("result, ", result)
    return result.choices[0].message['content']

def generate_all_and_save():
    for index in range(len(final_list)):
        try:
            current_text = final_list[index]['combined_text']
            previous_text = final_list[index]['prev_sentence']
            images = final_list[index]['images']
            prompt = generate_prompt(current_text, previous_text, images)
            answer = generate_answer(prompt)

            file_path = f"outputs/{index}.md"
            with open(file_path, 'w') as file:
                file.write(answer)

            print(f"Saved content for INDEX: {index}", file_path)
            time.sleep(60)
        except Exception as e:
            print(f'Error while processing INDEX: {index}, \n ERROR: {e}')

generate_all_and_save()

import os

directory = '/outputs/'
youtube_link = "https://youtu.be/zduSFxRajkE?si=6vm4GUe1GMvz4U1W&t="
combined_content = ''

for index in range(len(final_list)):
    filename = "{}.md".format(index)
    file_path = os.path.join(directory, filename)

    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            content = file.read()
            start_time = final_list[index]['start']
            end_time = final_list[index]['end']
            timestamp = f"{start_time} - {end_time} "
            combined_content = f"{combined_content} \n\n [{timestamp}]({youtube_link}{timestamp_to_seconds(start_time)}) \n\n {content}"
    else:
        print(f"File {filename} does not exist.")

with open("sample.md", "w") as file:
    file.write(combined_content)
