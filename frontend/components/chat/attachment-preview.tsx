'use client';

import * as React from 'react';
import { MediaLightbox } from './media-lightbox';

export function AttachmentPreview({ src, alt }: { src: string; alt: string }) {
  const [lightboxOpen, setLightboxOpen] = React.useState(false);

  return (
    <>
      <div
        className="mt-2 rounded-xl overflow-hidden max-w-[280px] cursor-pointer border border-white/10 shadow-sm group/img relative"
        onClick={() => setLightboxOpen(true)}
      >
        <img
          src={src}
          alt={alt}
          className="max-h-56 w-full object-cover transition-transform duration-300 group-hover/img:scale-105"
          loading="lazy"
        />
        <div className="absolute inset-0 bg-black/0 group-hover/img:bg-black/20 transition-colors" />
      </div>

      <MediaLightbox
        src={src}
        alt={alt}
        isOpen={lightboxOpen}
        onClose={() => setLightboxOpen(false)}
      />
    </>
  );
}
