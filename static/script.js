class YouTubeDownloader {
    constructor() {
        this.currentTaskId = null;
        this.currentVideoInfo = null;
        this.initializeEvents();
    }

    initializeEvents() {
        document.getElementById('getInfoBtn').addEventListener('click', () => this.getVideoInfo());
        document.getElementById('downloadBtn').addEventListener('click', () => this.startDownload());
        document.getElementById('finalDownloadBtn').addEventListener('click', () => this.downloadFile());
        
        document.getElementById('youtubeUrl').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.getVideoInfo();
        });

        // Show/hide quality options based on download type
        document.querySelectorAll('input[name="downloadType"]').forEach(radio => {
            radio.addEventListener('change', () => this.toggleQualityOptions());
        });

        this.toggleQualityOptions();
    }

    toggleQualityOptions() {
        const downloadType = document.querySelector('input[name="downloadType"]:checked').value;
        const qualityOptions = document.getElementById('qualityOptions');
        
        if (downloadType === 'video') {
            qualityOptions.style.display = 'block';
        } else {
            qualityOptions.style.display = 'none';
        }
    }

    async getVideoInfo() {
        const url = document.getElementById('youtubeUrl').value.trim();
        const btn = document.getElementById('getInfoBtn');
        
        if (!url) {
            this.showToast('Please enter a YouTube URL', 'error');
            return;
        }

        if (!this.isValidYouTubeUrl(url)) {
            this.showToast('Please enter a valid YouTube URL', 'error');
            return;
        }

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';

        try {
            const response = await fetch('/api/get_info', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: url })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error);
            }

            this.currentVideoInfo = data.video_info;
            this.displayVideoInfo(data.video_info);
            this.showToast('Video information loaded!', 'success');

        } catch (error) {
            this.showToast(error.message, 'error');
        }

        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-info-circle"></i> Get Info';
    }

    displayVideoInfo(info) {
        const videoInfoSection = document.getElementById('videoInfo');
        const thumbnail = document.getElementById('videoThumbnail');
        const title = document.getElementById('videoTitle');
        const uploader = document.getElementById('videoUploader');
        const duration = document.getElementById('videoDuration');
        const views = document.getElementById('videoViews');

        // Set video information
        thumbnail.src = info.thumbnail;
        thumbnail.alt = info.title;
        title.textContent = info.title;
        uploader.textContent = `By: ${info.uploader}`;
        duration.textContent = `Duration: ${this.formatDuration(info.duration)}`;
        views.textContent = `Views: ${this.formatViews(info.view_count)}`;

        videoInfoSection.classList.remove('hidden');
    }

    formatDuration(seconds) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
    }

    formatViews(views) {
        if (views >= 1000000) {
            return (views / 1000000).toFixed(1) + 'M';
        } else if (views >= 1000) {
            return (views / 1000).toFixed(1) + 'K';
        }
        return views;
    }

    async startDownload() {
        if (!this.currentVideoInfo) {
            this.showToast('Please get video information first', 'error');
            return;
        }

        const url = document.getElementById('youtubeUrl').value.trim();
        const downloadType = document.querySelector('input[name="downloadType"]:checked').value;
        const quality = document.getElementById('videoQuality').value;
        const btn = document.getElementById('downloadBtn');

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';

        try {
            const response = await fetch('/api/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    url: url,
                    type: downloadType,
                    quality: quality
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error);
            }

            this.currentTaskId = data.task_id;
            this.showProgress();
            this.startTracking();

            this.showToast(`Download started for ${downloadType.toUpperCase()}!`, 'success');

        } catch (error) {
            this.showToast(error.message, 'error');
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-download"></i> Start Download';
        }
    }

    isValidYouTubeUrl(url) {
        return /youtube\.com|youtu\.be/.test(url);
    }

    showProgress() {
        document.getElementById('progressSection').classList.remove('hidden');
        this.updateProgress(0, 'Starting...');
    }

    updateProgress(percent, text) {
        document.getElementById('progressFill').style.width = percent + '%';
        document.getElementById('progressText').textContent = text;
        document.getElementById('progressPercent').textContent = percent + '%';
    }

    async startTracking() {
        const interval = setInterval(async () => {
            if (!this.currentTaskId) {
                clearInterval(interval);
                return;
            }

            try {
                const response = await fetch(`/api/progress/${this.currentTaskId}`);
                const progress = await response.json();

                this.updateProgress(progress.percent, progress.message);

                if (progress.status === 'completed') {
                    clearInterval(interval);
                    this.showDownload();
                    this.showToast('Download completed!', 'success');
                    this.resetDownloadButton();
                } else if (progress.status === 'error') {
                    clearInterval(interval);
                    this.showToast(progress.message, 'error');
                    this.resetDownloadButton();
                }

            } catch (error) {
                console.error('Tracking error:', error);
            }
        }, 1000);
    }

    showDownload() {
        document.getElementById('downloadSection').classList.remove('hidden');
    }

    async downloadFile() {
        const btn = document.getElementById('finalDownloadBtn');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Downloading...';

        try {
            const response = await fetch(`/api/file/${this.currentTaskId}`);
            
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                
                // Get filename from content disposition or create one
                const contentDisposition = response.headers.get('content-disposition');
                let filename = `youtube_download_${this.currentTaskId}.mp3`;
                
                if (contentDisposition) {
                    const filenameMatch = contentDisposition.match(/filename="?(.+)"?/);
                    if (filenameMatch) {
                        filename = filenameMatch[1];
                    }
                }
                
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);

                this.showToast('Download started!', 'success');
            } else {
                throw new Error('Download failed');
            }

        } catch (error) {
            this.showToast('Download failed', 'error');
        }

        setTimeout(() => {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-file-download"></i> Download File';
        }, 3000);
    }

    resetDownloadButton() {
        const btn = document.getElementById('downloadBtn');
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-download"></i> Start Download';
    }

    showToast(message, type) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `toast ${type}`;
        toast.classList.remove('hidden');

        setTimeout(() => {
            toast.classList.add('hidden');
        }, 3000);
    }
}

// Start the application
document.addEventListener('DOMContentLoaded', () => {
    new YouTubeDownloader();
});