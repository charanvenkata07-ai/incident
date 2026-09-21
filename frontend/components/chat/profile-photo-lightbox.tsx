'use client';
import { X } from 'lucide-react';

interface ProfilePhotoLightboxProps {
  src: string;
  alt: string;
  onClose: () => void;
}

export function ProfilePhotoLightbox({ src, alt, onClose }: ProfilePhotoLightboxProps) {
  return (
    <div className="fixed inset-0 z-[200] bg-black/95 flex items-center justify-center" onClick={onClose}>
      <button type="button" onClick={onClose} className="absolute top-4 right-4 h-10 w-10 rounded-full bg-white/10 flex items-center justify-center text-white hover:bg-white/20 transition-colors">
        <X className="h-5 w-5" />
      </button>
      <img src={src} alt={alt} className="max-w-[90vw] max-h-[90vh] rounded-2xl object-contain shadow-2xl" onClick={e => e.stopPropagation()} />
    </div>
  );
}
