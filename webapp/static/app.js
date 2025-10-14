(function () {
  'use strict';

  const videoThumbs = document.querySelectorAll('[data-video-src]');
  if (!videoThumbs.length) {
    return;
  }

  const MAX_ACTIVE_LOADS = 2;
  let activeLoads = 0;
  const pendingLoads = [];

  const startNext = () => {
    if (activeLoads >= MAX_ACTIVE_LOADS) {
      return;
    }
    const next = pendingLoads.shift();
    if (!next) {
      return;
    }
    activeLoads += 1;
    next();
  };

  const finishLoad = (video, success) => {
    if (video.dataset.loadingState !== 'active' && video.dataset.loadingState !== 'pending') {
      return;
    }
    video.dataset.loadingState = success ? 'done' : 'idle';
    if (success) {
      video.dataset.loaded = 'true';
    }
    if (activeLoads > 0) {
      activeLoads -= 1;
    }
    startNext();
  };

  const loadVideo = (video) => {
    if (video.dataset.loaded === 'true' || video.dataset.loadingState === 'active' || video.dataset.loadingState === 'pending') {
      return;
    }

    const begin = () => {
      video.dataset.loadingState = 'active';
      const source = document.createElement('source');
      source.src = video.dataset.videoSrc;
      const type = video.dataset.videoType;
      if (type) {
        source.type = type;
      }
      video.appendChild(source);
      video.load();
    };

    if (activeLoads >= MAX_ACTIVE_LOADS) {
      video.dataset.loadingState = 'pending';
      pendingLoads.push(begin);
      return;
    }

    activeLoads += 1;
    begin();
  };

  const markReady = (video) => {
    video.pause();
    video.classList.add('is-ready');
    const wrapper = video.parentElement;
    if (wrapper) {
      const placeholder = wrapper.querySelector('.video-thumb-placeholder');
      if (placeholder) {
        placeholder.classList.add('is-hidden');
      }
    }
  };

  const attachVideoEvents = (video) => {
    video.addEventListener(
      'loadedmetadata',
      () => {
        markReady(video);
        finishLoad(video, true);
      },
      { once: true }
    );

    video.addEventListener('loadeddata', () => {
      markReady(video);
    });

    const handleError = () => {
      finishLoad(video, false);
    };
    video.addEventListener('error', handleError, { once: true });
    video.addEventListener('stalled', handleError, { once: true });
    video.addEventListener('abort', handleError, { once: true });

    const togglePlayback = (playing) => {
      if (!video.classList.contains('is-ready')) {
        return;
      }
      if (playing) {
        video.play().catch(() => {});
      } else {
        video.pause();
        if (video.currentTime && video.currentTime > 0.1) {
          try {
            video.currentTime = 0;
          } catch (err) {
            /* noop */
          }
        }
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
