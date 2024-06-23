from flask import Flask, Response, send_from_directory
from youtube_transcript_api import YouTubeTranscriptApi
import cv2, os, threading, time
from flask_cors import CORS

from functions import combine_transcript, download_video, timestamp_to_seconds, take_screenshot, compare_images, generate_prompt, generate_answer, get_video_info

app = Flask(__name__)
CORS(app)

@app.route('/')
def hello_world():
    return 'Hello, World!'

# Ensure the directory exists
SCREENSHOTS_FOLDER = os.path.join(os.getcwd(), 'screenshots')

@app.route('/screenshots/<path:filename>')
def serve_screenshot(filename):
    return send_from_directory(SCREENSHOTS_FOLDER, filename)

@app.route('/get_info/<video_id>')
def get_info(video_id):
    info = get_video_info(f"https://www.youtube.com/watch?v={video_id}")
    return info[0], 200

@app.route('/process/<video_id>')
def process(video_id):
    thread = threading.Thread(target=process_video, args=(video_id,))
    thread.start()
    print("Thread started. Processing video...")
    return "Processing started for video with ID: {}".format(video_id), 202

def process_video(video_id):
    transcript = YouTubeTranscriptApi.get_transcript(video_id)
    loaded_object = combine_transcript(transcript)
    
    download_video(video_id)
    video_path = 'videos/{}.mp4'.format(video_id)
    output_path = 'screenshots/'
    timestamp_in_seconds = [timestamp_to_seconds(time['start']) for time in loaded_object]

    take_screenshot(video_path, output_path, timestamp_in_seconds, video_id)

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
                prev_image_path = f"screenshots/{video_id}--{timestamp_to_seconds(loaded_object[i + j - 1]['start'])}.jpeg"
                curr_image_path = f"screenshots/{video_id}--{timestamp_to_seconds(loaded_object[i + j]['start'])}.jpeg"
                
                prev_image = cv2.imread(prev_image_path)
                curr_image = cv2.imread(curr_image_path)

                if prev_image is None or curr_image is None:
                    print(f"Warning: Could not read one of the images: {prev_image_path} or {curr_image_path}")
                    continue

                if compare_images(prev_image, curr_image) >= 10:
                    images.append(curr_image_path)

        final_list.append({'combined_text': combined_text, 'prev_sentence': prev, 'images': images, 'start': start, 'end': end})
    
    # Generate content for each interval (generate_all_and_save)
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
            # yield the content, so that the user can see the progress
            yield f"{index}_?/_/?_{answer} \n\n"
            time.sleep(60)
        except Exception as e:
            print(f'Error while processing INDEX: {index}, \n ERROR: {e}')

    directory = 'outputs/'
    youtube_link = "https://youtube.com/watch?v={}&t=".format(video_id)
    combined_content = ''

    for index in range(len(final_list)):
        filename = "{}.md".format(index)
        file_path = os.path.join(directory, filename)
        print("File path: ", file_path)

        if os.path.exists(file_path):
            with open(file_path, 'r') as file:
                content = file.read()
                start_time = final_list[index]['start']
                end_time = final_list[index]['end']
                timestamp = f"{start_time} - {end_time} "
                combined_content = f"{combined_content} \n\n [{timestamp}]({youtube_link}{timestamp_to_seconds(start_time)}) \n\n {content}"
        else:
            print(f"File {file_path} does not exist.")
    
    with open("sample.md", "w") as file:
        file.write(combined_content)
    
    res = {
        "video_id": video_id,
        "youtube_link": youtube_link,
        "combined_content": combined_content
    }

    return res, 200

@app.route('/stream/<video_id>')
def stream(video_id):
    return Response(process_video(video_id), content_type='text/plain')


if __name__ == '__main__':
    app.run()
    