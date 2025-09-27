#power by tharu adimn
from flask import Flask, render_template, request, send_file, jsonify, flash, redirect, url_for
import os
import yt_dlp
import threading
import time
import uuid
import re
from urllib.parse import urlparse
import json
import atexit
from threading import Timer

app = Flask(__name__)
app.config['SECRET_KEY'] = '563d05009317e79d1c226dce152530dc'
app.config['DOWNLOAD_FOLDER'] = 'static/downloads/'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

# Create downloads folder
if not os.path.exists(app.config['DOWNLOAD_FOLDER']):
    os.makedirs(app.config['DOWNLOAD_FOLDER'])

class DownloadManager:
    def __init__(self):
        self.progress = {}
        self.files = {}
        self.video_info = {}
        self.cleanup_scheduled = False
    
    def update_progress(self, task_id, status, percent=0, message=""):
        self.progress[task_id] = {
            'status': status,
            'percent': percent,
            'message': message,
            'timestamp': time.time()
        }
    
    def get_progress(self, task_id):
        return self.progress.get(task_id, {'status': 'unknown', 'percent': 0, 'message': ''})
    
    def set_file(self, task_id, filename, file_type='mp3'):
        self.files[task_id] = {
            'filename': filename,
            'type': file_type,
            'created_at': time.time(),
            'downloaded': False
        }
    
    def get_file(self, task_id):
        file_info = self.files.get(task_id)
        if file_info:
            # Mark as downloaded when user accesses the file
            file_info['downloaded'] = True
            file_info['downloaded_at'] = time.time()
            
            # Schedule cleanup for this file after 30 seconds
            schedule_file_cleanup(file_info['filename'], 30)
            
        return file_info
    
    def set_video_info(self, task_id, info):
        self.video_info[task_id] = info
    
    def get_video_info(self, task_id):
        return self.video_info.get(task_id)
    
    def cleanup_old_files(self):
        """Cleanup files that are older than 1 hour"""
        current_time = time.time()
        files_to_remove = []
        
        # Clean files from memory
        for task_id, file_info in list(self.files.items()):
            if current_time - file_info.get('created_at', 0) > 3600:  # 1 hour
                files_to_remove.append((task_id, file_info['filename']))
        
        # Remove from memory
        for task_id, filename in files_to_remove:
            if task_id in self.files:
                del self.files[task_id]
            if task_id in self.progress:
                del self.progress[task_id]
            if task_id in self.video_info:
                del self.video_info[task_id]
        
        # Clean physical files that are older than 1 hour
        try:
            for filename in os.listdir(app.config['DOWNLOAD_FOLDER']):
                filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
                if os.path.isfile(filepath):
                    if current_time - os.path.getctime(filepath) > 3600:  # 1 hour
                        try:
                            os.remove(filepath)
                            print(f"🧹 Cleaned up old file: {filename}")
                        except Exception as e:
                            print(f"❌ Error cleaning file {filename}: {e}")
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")

download_manager = DownloadManager()

def schedule_file_cleanup(filename, delay_seconds=30):
    """Schedule a file to be deleted after specified delay"""
    def cleanup_file():
        try:
            if os.path.exists(filename):
                os.remove(filename)
                print(f"✅ Auto-cleaned downloaded file: {os.path.basename(filename)}")
                
                # Also remove from download manager
                for task_id, file_info in list(download_manager.files.items()):
                    if file_info.get('filename') == filename:
                        if task_id in download_manager.files:
                            del download_manager.files[task_id]
                        if task_id in download_manager.progress:
                            del download_manager.progress[task_id]
                        break
                        
        except Exception as e:
            print(f"❌ Error auto-cleaning file {filename}: {e}")
    
    # Schedule the cleanup
    Timer(delay_seconds, cleanup_file).start()

def auto_cleanup_old_files():
    """Automatically cleanup old files every 5 minutes"""
    download_manager.cleanup_old_files()
    # Schedule next cleanup
    Timer(300, auto_cleanup_old_files).start()  # 5 minutes

def clean_filename(filename):
    """Clean filename to remove invalid characters"""
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    # Remove extra spaces and limit length
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename[:100]  # Limit filename length

def get_video_info(video_url):
    """Get video information without downloading"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            # Extract available formats
            formats = []
            if 'formats' in info:
                for f in info['formats']:
                    if f.get('filesize') or f.get('filesize_approx'):
                        format_info = {
                            'format_id': f['format_id'],
                            'ext': f['ext'],
                            'quality': f.get('format_note', 'Unknown'),
                            'filesize': f.get('filesize', f.get('filesize_approx', 0)),
                            'resolution': f.get('height', 'Unknown'),
                            'acodec': f.get('acodec', 'none'),
                            'vcodec': f.get('vcodec', 'none')
                        }
                        formats.append(format_info)
            
            video_data = {
                'title': info.get('title', 'Unknown Title'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'formats': formats
            }
            
            return video_data
    except Exception as e:
        return {'error': str(e)}

def youtube_downloader(video_url, task_id, download_type='mp3', quality='best'):
    try:
        download_manager.update_progress(task_id, 'starting', 10, 'Processing video...')
        
        if download_type == 'mp3':
            # MP3 Download
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(app.config['DOWNLOAD_FOLDER'], '%(title)s') + f'_{task_id}.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'noplaylist': True,
                'quiet': True,
            }
        else:
            # Video Download
            if quality == 'best':
                ydl_opts = {
                    'format': 'best[height<=1080]',
                    'outtmpl': os.path.join(app.config['DOWNLOAD_FOLDER'], '%(title)s') + f'_{task_id}.%(ext)s',
                    'noplaylist': True,
                    'quiet': True,
                }
            elif quality == '720p':
                ydl_opts = {
                    'format': 'best[height<=720]',
                    'outtmpl': os.path.join(app.config['DOWNLOAD_FOLDER'], '%(title)s') + f'_{task_id}.%(ext)s',
                    'noplaylist': True,
                    'quiet': True,
                }
            elif quality == '480p':
                ydl_opts = {
                    'format': 'best[height<=480]',
                    'outtmpl': os.path.join(app.config['DOWNLOAD_FOLDER'], '%(title)s') + f'_{task_id}.%(ext)s',
                    'noplaylist': True,
                    'quiet': True,
                }
            elif quality == '360p':
                ydl_opts = {
                    'format': 'best[height<=360]',
                    'outtmpl': os.path.join(app.config['DOWNLOAD_FOLDER'], '%(title)s') + f'_{task_id}.%(ext)s',
                    'noplaylist': True,
                    'quiet': True,
                }
            else:
                ydl_opts = {
                    'format': 'best[height<=1080]',
                    'outtmpl': os.path.join(app.config['DOWNLOAD_FOLDER'], '%(title)s') + f'_{task_id}.%(ext)s',
                    'noplaylist': True,
                    'quiet': True,
                }
        
        def progress_hook(d):
            if d['status'] == 'downloading':
                if d.get('total_bytes'):
                    percent = int(d['downloaded_bytes'] / d['total_bytes'] * 100)
                    download_manager.update_progress(task_id, 'downloading', 30 + int(percent * 0.6), 
                                                   f'Downloading... {percent}%')
                else:
                    download_manager.update_progress(task_id, 'downloading', 50, 'Downloading...')
            elif d['status'] == 'finished':
                if download_type == 'mp3':
                    download_manager.update_progress(task_id, 'converting', 90, 'Converting to MP3...')
                else:
                    download_manager.update_progress(task_id, 'processing', 90, 'Finalizing video...')
        
        ydl_opts['progress_hooks'] = [progress_hook]
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Get video info first
            download_manager.update_progress(task_id, 'processing', 20, 'Getting video info...')
            info = ydl.extract_info(video_url, download=False)
            video_title = info.get('title', 'Unknown Title')
            
            # Start download
            download_manager.update_progress(task_id, 'downloading', 30, 'Starting download...')
            ydl.download([video_url])
            
            # Find the downloaded file
            expected_filename = ydl.prepare_filename(info)
            
            if download_type == 'mp3':
                final_filename = os.path.splitext(expected_filename)[0] + '.mp3'
                file_type = 'mp3'
            else:
                final_filename = expected_filename
                file_type = 'video'
            
            if os.path.exists(final_filename):
                download_manager.set_file(task_id, final_filename, file_type)
                download_manager.update_progress(task_id, 'completed', 100, 'Ready to download!')
                
                # Schedule cleanup for this file after 1 hour if not downloaded
                schedule_file_cleanup(final_filename, 3600)
                
                print(f"✅ Download completed: {os.path.basename(final_filename)}")
                
            else:
                download_manager.update_progress(task_id, 'error', 0, 'File not found after download')
                print(f"❌ File not found: {expected_filename}")
                
    except Exception as e:
        error_msg = str(e)
        download_manager.update_progress(task_id, 'error', 0, f"Download error: {error_msg}")
        print(f"❌ Download error: {error_msg}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/get_info', methods=['POST'])
def api_get_info():
    try:
        data = request.get_json()
        youtube_url = data.get('url', '').strip()
        
        if not youtube_url:
            return jsonify({'error': 'Please enter a YouTube URL'}), 400
        
        # Validate URL
        if not any(domain in youtube_url for domain in ['youtube.com', 'youtu.be']):
            return jsonify({'error': 'Please enter a valid YouTube URL'}), 400
        
        # Get video information
        video_info = get_video_info(youtube_url)
        
        if 'error' in video_info:
            return jsonify({'error': video_info['error']}), 400
        
        return jsonify({
            'success': True,
            'video_info': video_info
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def api_download():
    try:
        data = request.get_json()
        youtube_url = data.get('url', '').strip()
        download_type = data.get('type', 'mp3')
        quality = data.get('quality', 'best')
        
        if not youtube_url:
            return jsonify({'error': 'Please enter a YouTube URL'}), 400
        
        # Validate URL
        if not any(domain in youtube_url for domain in ['youtube.com', 'youtu.be']):
            return jsonify({'error': 'Please enter a valid YouTube URL'}), 400
        
        # Generate unique task ID
        task_id = str(uuid.uuid4())[:8]
        
        # Start download in background thread
        thread = threading.Thread(target=youtube_downloader, args=(youtube_url, task_id, download_type, quality))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'{download_type.upper()} download started'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/progress/<task_id>')
def api_progress(task_id):
    progress = download_manager.get_progress(task_id)
    return jsonify(progress)

@app.route('/api/file/<task_id>')
def api_file(task_id):
    try:
        file_info = download_manager.get_file(task_id)
        if file_info and os.path.exists(file_info['filename']):
            # Clean filename for download
            clean_name = os.path.basename(file_info['filename'])
            
            print(f"📥 User downloading file: {clean_name}")
            
            # Send file and it will be automatically cleaned up after download
            response = send_file(file_info['filename'], as_attachment=True, download_name=clean_name)
            
            return response
        else:
            return jsonify({'error': 'File not found'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cleanup', methods=['POST'])
def api_cleanup():
    try:
        download_manager.cleanup_old_files()
        return jsonify({'success': True, 'message': 'Cleanup completed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def api_status():
    """Get server status and file count"""
    try:
        file_count = len([name for name in os.listdir(app.config['DOWNLOAD_FOLDER']) 
                         if os.path.isfile(os.path.join(app.config['DOWNLOAD_FOLDER'], name))])
        
        return jsonify({
            'status': 'running',
            'files_in_folder': file_count,
            'active_downloads': len(download_manager.progress),
            'timestamp': time.time()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.before_request
def before_first_request():
    """Initialize cleanup on first request"""
    if not hasattr(app, 'cleanup_initialized'):
        app.cleanup_initialized = True
        # Initial cleanup
        download_manager.cleanup_old_files()
        # Start automatic cleanup scheduler
        Timer(10, auto_cleanup_old_files).start()  # Start after 10 seconds
        print("✅ Auto-cleanup system initialized")

# Cleanup on exit
def exit_cleanup():
    """Cleanup all files on exit"""
    try:
        for filename in os.listdir(app.config['DOWNLOAD_FOLDER']):
            filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
        print("✅ All files cleaned up on exit")
    except Exception as e:
        print(f"❌ Error during exit cleanup: {e}")

# Register exit handler
atexit.register(exit_cleanup)

if __name__ == '__main__':
    print("🚀 YouTube Downloader & Converter Started!")
    print("📱 Access on: http://127.0.0.1:5010")
    print("✨ Features: MP3 Conversion, Video Download (Multiple Qualities)")
    print("🧹 Auto-Cleanup: Downloaded files are automatically deleted")
    print("⏰ Files auto-delete 30 seconds after user download")
    
    # Initial folder cleanup
    download_manager.cleanup_old_files()
    
    app.run(debug=True, host='0.0.0.0', port=5010)