'use client';
import * as React from 'react';
import { X, Mail, Phone, Clock, Shield, MessageSquare } from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { ProfilePhotoLightbox } from './profile-photo-lightbox';
import type { TeamMemberBrief } from './types';

interface ProfileDrawerProps {
  member: TeamMemberBrief;
  open: boolean;
  onClose: () => void;
  onMessage: (member: TeamMemberBrief) => void;
  getMediaUrl: (url: string) => string;
}

export function ProfileDrawer({ member, open, onClose, onMessage, getMediaUrl }: ProfileDrawerProps) {
  const [lightboxOpen, setLightboxOpen] = React.useState(false);
  const avatarSrc = member.avatar_url ? (member.avatar_url.startsWith('http') ? member.avatar_url : getMediaUrl(member.avatar_url)) : undefined;
  const isAvailable = member.is_present && member.availability_status === 'AVAILABLE';
  const isBusy = member.is_present && member.availability_status !== 'AVAILABLE';

  return (
    <>
      {open && <div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" onClick={onClose} />}
      <div className={`fixed top-0 right-0 h-full w-80 z-50 bg-[#071426] border-l border-white/10 shadow-2xl transform transition-transform duration-300 ${open ? 'translate-x-0' : 'translate-x-full'} flex flex-col`}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <span className="text-sm font-bold text-white">Profile</span>
          <button type="button" onClick={onClose} className="h-8 w-8 rounded-xl flex items-center justify-center text-white/40 hover:text-white hover:bg-white/10 transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          <div className="flex flex-col items-center gap-3 pt-4">
            <button type="button" onClick={() => avatarSrc && setLightboxOpen(true)} className="relative">
              <Avatar className="h-20 w-20 border-2 border-[#087CFF]/30">
                {avatarSrc && <AvatarImage src={avatarSrc} alt={member.full_name} />}
                <AvatarFallback className="text-2xl font-bold bg-[#0B1B31] text-white/70">{member.full_name?.charAt(0) || 'U'}</AvatarFallback>
              </Avatar>
              <span className={`absolute bottom-1 right-1 w-3.5 h-3.5 rounded-full ring-2 ring-[#071426] ${isAvailable ? 'bg-emerald-500' : isBusy ? 'bg-amber-500' : 'bg-zinc-600'}`} />
            </button>
            <div className="text-center">
              <div className="flex items-center gap-1.5 justify-center">
                <h3 className="text-base font-bold text-white">{member.full_name}</h3>
                {member.is_group_leader && <Shield className="h-4 w-4 text-amber-400" />}
              </div>
              <p className="text-xs text-white/40 mt-0.5">{member.is_present ? member.availability_status : 'Offline'}</p>
            </div>
          </div>
          <div className="space-y-3">
            {member.email && <div className="flex items-center gap-3"><Mail className="h-4 w-4 text-white/30 flex-shrink-0" /><span className="text-xs text-white/70 truncate">{member.email}</span></div>}
            {member.phone && <div className="flex items-center gap-3"><Phone className="h-4 w-4 text-white/30 flex-shrink-0" /><span className="text-xs text-white/70">{member.phone}</span></div>}
            {member.timezone && <div className="flex items-center gap-3"><Clock className="h-4 w-4 text-white/30 flex-shrink-0" /><span className="text-xs text-white/70">{member.timezone}</span></div>}
            {member.current_shift_name && <div className="flex items-center gap-3"><Clock className="h-4 w-4 text-white/30 flex-shrink-0" /><span className="text-xs text-white/70">Shift: {member.current_shift_name}</span></div>}
          </div>
          {member.bio && <div className="p-3 bg-white/5 rounded-xl"><p className="text-xs text-white/50 italic">&ldquo;{member.bio}&rdquo;</p></div>}
        </div>
        <div className="p-4 border-t border-white/10">
          <button type="button" onClick={() => { onMessage(member); onClose(); }}
            className="w-full flex items-center justify-center gap-2 bg-[#087CFF] hover:bg-[#0070e0] text-white text-sm font-semibold py-2.5 rounded-xl transition-colors">
            <MessageSquare className="h-4 w-4" />
            Send Message
          </button>
        </div>
      </div>
      {lightboxOpen && avatarSrc && <ProfilePhotoLightbox src={avatarSrc} alt={member.full_name} onClose={() => setLightboxOpen(false)} />}
    </>
  );
}
