(function () {
  'use strict';

  const thumbs = document.querySelectorAll('[data-thumb-img]');
  if (!thumbs.length) {
    return;
  }

  const markReady = (img) => {
    img.classList.add('is-ready');
    const wrapper = img.closest('.video-thumb-wrapper');
    if (!wrapper) {
      return;
    }
    const placeholder = wrapper.querySelector('.video-thumb-placeholder');
    if (placeholder) {
      placeholder.classList.add('is-hidden');
    }
  };

  const markError = (img) => {
    const wrapper = img.closest('.video-thumb-wrapper');
    if (wrapper) {
      wrapper.classList.add('thumb-error');
      const placeholder = wrapper.querySelector('.video-thumb-placeholder');
      if (placeholder) {
        placeholder.classList.remove('is-hidden');
      }
    }
  };

  thumbs.forEach((img) => {
    if (img.complete && img.naturalWidth > 0 && img.naturalHeight > 0) {
      markReady(img);
      return;
    }
    img.addEventListener('load', () => markReady(img), { once: true });
    img.addEventListener('error', () => markError(img), { once: true });
  });
})();
