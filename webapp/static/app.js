(function () {
  'use strict';

  const videoThumbs = document.querySelectorAll('[data-video-src]');
  const mainPlayer = document.querySelector('.video-player[data-player]');

  const markPlaceholderReady = (video) => {
    video.classList.add('is-ready');
    const wrapper = video.parentElement;
    if (!wrapper) {
      return;
    }
    const placeholder = wrapper.querySelector('.video-thumb-placeholder, .video-player-placeholder');
    if (placeholder) {
      placeholder.classList.add('is-hidden');
    }
  };

  if (mainPlayer) {
    const placeholder = mainPlayer.parentElement?.querySelector('.video-player-placeholder');
    const reveal = () => {
      markPlaceholderReady(mainPlayer);
    };
    mainPlayer.addEventListener('loadeddata', reveal, { once: true });
    mainPlayer.addEventListener('canplay', reveal, { once: true });
    if (mainPlayer.readyState >= 3) {
      reveal();
    }
    if (placeholder) {
      mainPlayer.addEventListener(
        'error',
        () => {
          placeholder.classList.remove('is-hidden');
          placeholder.classList.add('has-error');
          const spinner = placeholder.querySelector('.spinner-border');
          if (spinner) {
            spinner.classList.add('visually-hidden');
          }
          const text = placeholder.querySelector('.placeholder-text');
          if (text) {
            text.textContent = 'Unable to load video. Please try again later.';
          }
        },
        { once: true }
      );
    }
  }

  if (!videoThumbs.length) {
    return;
  }

  const loadVideo = (video) => {
    if (video.dataset.loaded === 'true') {
      return;
    }
    const source = document.createElement('source');
    source.src = video.dataset.videoSrc;
    const type = video.dataset.videoType;
    if (type) {
      source.type = type;
    }
    video.appendChild(source);
    video.dataset.loaded = 'true';
    video.load();
  };

  const prepareFrame = (video) => {
    const previewSecond = parseFloat(video.dataset.previewSecond || '1');
    if (!Number.isFinite(previewSecond)) {
      return;
    }
    const seekTime = Math.min(Math.max(previewSecond, 0), video.duration || previewSecond);
    if (seekTime > 0 && video.currentTime !== seekTime) {
      video.currentTime = seekTime;
    }
  };

  const markReady = (video) => {
    video.pause();
    markPlaceholderReady(video);
  };

  const attachVideoEvents = (video) => {
    video.addEventListener('loadedmetadata', () => {
      prepareFrame(video);
    });

    video.addEventListener('loadeddata', () => {
      if (!video.classList.contains('is-ready')) {
        markReady(video);
      }
    });

    video.addEventListener(
      'seeked',
      () => {
        if (!video.classList.contains('is-ready')) {
          markReady(video);
        }
      },
      { once: true }
    );

    const togglePlayback = (playing) => {
      if (!video.classList.contains('is-ready')) {
        return;
      }
      if (playing) {
        video.play().catch(() => {});
      } else {
        video.pause();
      }
    };

    video.addEventListener('mouseenter', () => togglePlayback(true));
    video.addEventListener('focus', () => togglePlayback(true));
    video.addEventListener('mouseleave', () => togglePlayback(false));
    video.addEventListener('blur', () => togglePlayback(false));
  };

  const observer = 'IntersectionObserver' in window
    ? new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              const video = entry.target;
              loadVideo(video);
              observer.unobserve(video);
            }
          });
        },
        { rootMargin: '150px', threshold: 0.15 }
      )
    : null;

  videoThumbs.forEach((video) => {
    attachVideoEvents(video);
    if (observer) {
      observer.observe(video);
    } else {
      loadVideo(video);
    }
  });
})();
