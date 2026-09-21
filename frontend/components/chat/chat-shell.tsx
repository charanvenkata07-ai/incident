'use client';

import * as React from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/use-auth';
import { apiClient } from '@/lib/api-client';
import { wsClient } from '@/lib/websocket';
import { toast } from 'sonner';
import { useChatContext } from '@/context/chat-context';
import { usePageSearch } from '@/hooks/use-page-search';
import { UploadCloud } from 'lucide-react';

import { ChatSidebar } from './chat-sidebar';
import { ConversationHeader } from './conversation-header';
import { MessageList } from './message-list';
import { TypingIndicator } from './typing-indicator';
import { ReplyBar } from './reply-bar';
import { VoiceRecorder } from './voice-recorder';
import { MessageComposer } from './message-composer';
import { EmptyChatState } from './empty-chat-state';
import { ProfileDrawer } from './profile-drawer';

import type {
  ChatMessage, ConversationItem, TeamMemberBrief,
  MyTeamChatData, ChatAttachment, ConversationTabType
} from './types';

// Group Leader Moderation Modal — inline to avoid extra file
function ModerationModal({ message, onConfirm, onCancel }: {
  message: ChatMessage;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = React.useState('Inappropriate or sensitive content');
  return (
    <div className="fixed inset-0 z-[60] bg-black/80 flex items-center justify-center p-4">
      <div className="bg-[#071426] border border-white/10 rounded-2xl p-5 w-full max-w-md shadow-2xl space-y-4">
        <h3 className="text-sm font-bold text-rose-400">Remove Message as Group Leader</h3>
        <div className="p-3 bg-white/5 rounded-xl text-xs space-y-1">
          <div className="font-semibold text-white/70">Author: {message.sender_name}</div>
          <div className="text-white/50 italic border-l-2 border-white/20 pl-2">&ldquo;{message.content}&rdquo;</div>
        </div>
        <div>
          <label className="text-xs font-semibold text-white/50 block mb-1">Reason</label>
          <select value={reason} onChange={e => setReason(e.target.value)}
            className="w-full h-9 border border-white/10 rounded-lg px-3 text-xs bg-[#0B1B31] text-white focus:outline-none">
            <option>Inappropriate or sensitive content</option>
            <option>Off-topic / spam</option>
            <option>Confidentiality breach</option>
            <option>Group Leader discretion</option>
          </select>
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onCancel} className="px-4 py-2 text-xs text-white/50 hover:text-white rounded-lg hover:bg-white/5 transition-colors">Cancel</button>
          <button type="button" onClick={() => onConfirm(reason)} className="px-4 py-2 text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white rounded-lg transition-colors">Confirm Removal</button>
        </div>
      </div>
    </div>
  );
}

export function ChatShell({ defaultTab }: { defaultTab?: ConversationTabType }) {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { setActiveConversationId, openProfileDrawer, profileDrawerOpen, profileDrawerUser, closeProfileDrawer } = useChatContext();

  const conversationParam = searchParams.get('conversation');
  const messageParam = searchParams.get('message');
  const focusParam = searchParams.get('focus');

  const [conversations, setConversations] = React.useState<ConversationItem[]>([]);
  const [myTeam, setMyTeam] = React.useState<MyTeamChatData | null>(null);
  const [colleagues, setColleagues] = React.useState<TeamMemberBrief[]>([]);
  const [selectedConvId, setSelectedConvIdState] = React.useState<string | null>(conversationParam || null);
  const [activeTab, setActiveTab] = React.useState<ConversationTabType>(defaultTab || 'TEAM');
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [newMessageText, setNewMessageText] = React.useState('');
  const [isLoadingConv, setIsLoadingConv] = React.useState(true);
  const [isLoadingMessages, setIsLoadingMessages] = React.useState(false);
  const [isSending, setIsSending] = React.useState(false);
  const [replyingTo, setReplyingTo] = React.useState<ChatMessage | null>(null);
  const [pendingAttachment, setPendingAttachment] = React.useState<ChatAttachment | null>(null);
  const [isUploadingAttachment, setIsUploadingAttachment] = React.useState(false);
  const [uploadProgress, setUploadProgress] = React.useState(0);
  const [isDraggingFile, setIsDraggingFile] = React.useState(false);
  const dragCounterRef = React.useRef(0);
  const [isRecording, setIsRecording] = React.useState(false);
  const [recordingDuration, setRecordingDuration] = React.useState(0);
  const [typingUsers, setTypingUsers] = React.useState<Record<string, string[]>>({});
  const [highlightedMessageId, setHighlightedMessageId] = React.useState<string | null>(messageParam || null);
  const [moderatingMessage, setModeratingMessage] = React.useState<ChatMessage | null>(null);
  const [isModerating, setIsModerating] = React.useState(false);
  const [currentUserProfile, setCurrentUserProfile] = React.useState<{ is_group_leader: boolean } | null>(null);
  // Mobile: show sidebar or conversation
  const [showMobileSidebar, setShowMobileSidebar] = React.useState(true);

  const messagesEndRef = React.useRef<HTMLDivElement>(null);
  const composerInputRef = React.useRef<HTMLInputElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const mediaRecorderRef = React.useRef<MediaRecorder | null>(null);
  const audioChunksRef = React.useRef<Blob[]>([]);
  const recordingTimerRef = React.useRef<NodeJS.Timeout | null>(null);
  const typingTimeoutRef = React.useRef<NodeJS.Timeout | null>(null);

  const isAdmin = user?.role === 'ADMIN' || user?.role === 'SUPERVISOR';
  const isLeader = Boolean(currentUserProfile?.is_group_leader || isAdmin);

  const scrollToBottom = React.useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  const scrollToMessage = (msgId: string) => {
    const el = document.getElementById(`msg-${msgId}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setHighlightedMessageId(msgId);
      setTimeout(() => setHighlightedMessageId(null), 3000);
    }
  };

  const setSelectedConvId = React.useCallback((id: string | null) => {
    setSelectedConvIdState(id);
    setActiveConversationId(id);
    if (id) setShowMobileSidebar(false);
  }, [setActiveConversationId]);

  // Fetch current user profile
  React.useEffect(() => {
    apiClient.get<{ is_group_leader: boolean }>('/api/me/profile').then(res => setCurrentUserProfile(res)).catch(() => {});
  }, []);

  const loadMyTeamChat = React.useCallback(async () => {
    try {
      const data = await apiClient.get<MyTeamChatData>('/api/chat/my-team');
      setMyTeam(data);
      if (!selectedConvId && !conversationParam) {
        setSelectedConvId(data.conversation_id);
      }
    } catch {}
  }, [selectedConvId, conversationParam, setSelectedConvId]);

  const loadConversations = React.useCallback(async () => {
    setIsLoadingConv(true);
    try {
      const data = await apiClient.get<ConversationItem[]>('/api/chat/conversations');
      setConversations(data || []);
    } catch (err: unknown) {
      const e = err as { message?: string };
      toast.error(e?.message || 'Failed to load conversations');
    } finally {
      setIsLoadingConv(false);
    }
  }, []);

  const loadColleagues = React.useCallback(async () => {
    try {
      const data = await apiClient.get<TeamMemberBrief[]>('/api/chat/team-members');
      setColleagues(data || []);
    } catch {}
  }, []);

  const loadMessages = React.useCallback(async (convId: string) => {
    setIsLoadingMessages(true);
    try {
      const data = await apiClient.get<ChatMessage[]>(`/api/chat/conversations/${convId}/messages`);
      const seen = new Set<string>();
      const unique = (data || []).filter((m: ChatMessage) => {
        if (seen.has(m.id)) return false;
        seen.add(m.id);
        return true;
      });
      setMessages(unique);
      await apiClient.post(`/api/chat/conversations/${convId}/read`, {});
      setConversations(prev => prev.map(c => c.id === convId ? { ...c, unread_count: 0 } : c));
    } catch (err: unknown) {
      const e = err as { message?: string };
      toast.error(e?.message || 'Failed to load messages');
    } finally {
      setIsLoadingMessages(false);
      if (messageParam) {
        setTimeout(() => scrollToMessage(messageParam), 150);
      } else {
        setTimeout(scrollToBottom, 100);
      }
      if (focusParam === 'composer') {
        setTimeout(() => composerInputRef.current?.focus(), 250);
      }
    }
  }, [messageParam, focusParam, scrollToBottom]);

  React.useEffect(() => {
    loadMyTeamChat();
    loadConversations();
    loadColleagues();
  }, [loadMyTeamChat, loadConversations, loadColleagues]);

  React.useEffect(() => {
    if (selectedConvId) {
      loadMessages(selectedConvId);
      setReplyingTo(null);
      setPendingAttachment(null);
    }
  }, [selectedConvId, loadMessages]);

  // Navigate to conversation from notification popup
  React.useEffect(() => {
    const handler = (e: Event) => {
      const custom = e as CustomEvent<{ conversationId: string }>;
      const cid = custom.detail.conversationId;
      if (cid) {
        setSelectedConvId(cid);
        // Switch to correct tab
        const conv = conversations.find(c => c.id === cid);
        if (conv) setActiveTab(conv.type === 'DIRECT' ? 'DIRECT' : 'TEAM');
      }
    };
    window.addEventListener('incidentflow:navigate-to-conversation', handler);
    return () => window.removeEventListener('incidentflow:navigate-to-conversation', handler);
  }, [conversations, setSelectedConvId]);

  // WebSocket listeners
  React.useEffect(() => {
    const handleIncomingMessage = (msg: unknown) => {
      const m = msg as ChatMessage;
      if (m.conversation_id === selectedConvId) {
        setMessages(prev => {
          if (prev.some(x => x.id === m.id)) return prev;
          return [...prev, m];
        });
        setTimeout(scrollToBottom, 80);
      }
      setConversations(prev => prev.map(c => {
        if (c.id === m.conversation_id) {
          return { ...c, last_message: m, unread_count: m.conversation_id === selectedConvId ? 0 : c.unread_count + 1 };
        }
        return c;
      }));
    };

    const handleMessageUpdated = (data: unknown) => {
      const d = data as Partial<ChatMessage>;
      setMessages(prev => prev.map(m => m.id === d.id ? { ...m, content: d.content || m.content, is_edited: d.is_edited ?? true, edited_at: d.edited_at } : m));
    };

    const handleMessageDeleted = (data: unknown) => {
      const d = data as Partial<ChatMessage>;
      setMessages(prev => prev.map(m => m.id === d.id ? { ...m, content: 'This message was deleted', is_deleted: true, deleted_at: d.deleted_at } : m));
    };

    const handleReactionAdded = (data: unknown) => {
      const d = data as { message_id: string; emoji: string; user_id: string };
      setMessages(prev => prev.map(m => {
        if (m.id !== d.message_id) return m;
        const reactions = m.reactions ? [...m.reactions] : [];
        const idx = reactions.findIndex(r => r.emoji === d.emoji);
        if (idx > -1) {
          const r = reactions[idx];
          const users = r.users.includes(d.user_id) ? r.users : [...r.users, d.user_id];
          reactions[idx] = { ...r, count: users.length, users };
        } else {
          reactions.push({ emoji: d.emoji, count: 1, users: [d.user_id] });
        }
        const user_reactions = d.user_id === user?.id ? Array.from(new Set([...(m.user_reactions || []), d.emoji])) : m.user_reactions || [];
        return { ...m, reactions, user_reactions };
      }));
    };

    const handleReactionRemoved = (data: unknown) => {
      const d = data as { message_id: string; emoji: string; user_id: string };
      setMessages(prev => prev.map(m => {
        if (m.id !== d.message_id) return m;
        const reactions = (m.reactions || []).map(r => {
          if (r.emoji !== d.emoji) return r;
          const users = r.users.filter(uid => uid !== d.user_id);
          return { ...r, count: users.length, users };
        }).filter(r => r.count > 0);
        const user_reactions = d.user_id === user?.id ? (m.user_reactions || []).filter(e => e !== d.emoji) : m.user_reactions || [];
        return { ...m, reactions, user_reactions };
      }));
    };

    const handleTyping = (data: unknown) => {
      const d = data as { conversation_id: string; user_id: string; user_name: string; is_typing: boolean };
      if (d?.conversation_id && d?.user_id !== user?.id) {
        setTypingUsers(prev => {
          const current = prev[d.conversation_id] || [];
          if (d.is_typing) {
            if (!current.includes(d.user_name)) return { ...prev, [d.conversation_id]: [...current, d.user_name] };
          } else {
            return { ...prev, [d.conversation_id]: current.filter(n => n !== d.user_name) };
          }
          return prev;
        });
        setTimeout(() => {
          setTypingUsers(prev => ({ ...prev, [d.conversation_id]: (prev[d.conversation_id] || []).filter(n => n !== d.user_name) }));
        }, 3000);
      }
    };

    const handleProfileUpdated = (data: unknown) => {
      const d = data as Partial<TeamMemberBrief>;
      setColleagues(prev => prev.map(c => {
        if (c.user_id !== d.user_id) return c;
        return { ...c, full_name: d.full_name || c.full_name, avatar_url: d.avatar_url ?? c.avatar_url, is_present: d.is_present ?? c.is_present, availability_status: d.availability_status ?? c.availability_status, is_group_leader: d.is_group_leader ?? c.is_group_leader };
      }));
    };

    const handleGroupLeaderChanged = (data: unknown) => {
      const d = data as { new_leader?: { user_id: string; full_name: string; employee_id?: string }; old_leader_user_id?: string };
      if (!d) return;
      if (d.new_leader?.user_id === user?.id) {
        setCurrentUserProfile({ is_group_leader: true });
        toast.success('👑 You are now the Group Leader!');
      } else if (d.old_leader_user_id === user?.id) {
        setCurrentUserProfile({ is_group_leader: false });
        toast.info('Group leadership transferred to ' + (d.new_leader?.full_name || 'a teammate'));
      }
      setColleagues(prev => prev.map(c => ({ ...c, is_group_leader: c.user_id === d.new_leader?.user_id || c.employee_id === d.new_leader?.employee_id })));
      loadConversations();
      loadColleagues();
    };

    wsClient.on('CHAT_MESSAGE_CREATED', handleIncomingMessage);
    wsClient.on('CHAT_MESSAGE_UPDATED', handleMessageUpdated);
    wsClient.on('CHAT_MESSAGE_DELETED', handleMessageDeleted);
    wsClient.on('CHAT_MESSAGE_REACTION_ADDED', handleReactionAdded);
    wsClient.on('CHAT_MESSAGE_REACTION_REMOVED', handleReactionRemoved);
    wsClient.on('CHAT_TYPING', handleTyping);
    wsClient.on('PROFILE_UPDATED', handleProfileUpdated);
    wsClient.on('TEAM_MEMBER_UPDATED', handleProfileUpdated);
    wsClient.on('GROUP_LEADER_CHANGED', handleGroupLeaderChanged);

    return () => {
      wsClient.off('CHAT_MESSAGE_CREATED', handleIncomingMessage);
      wsClient.off('CHAT_MESSAGE_UPDATED', handleMessageUpdated);
      wsClient.off('CHAT_MESSAGE_DELETED', handleMessageDeleted);
      wsClient.off('CHAT_MESSAGE_REACTION_ADDED', handleReactionAdded);
      wsClient.off('CHAT_MESSAGE_REACTION_REMOVED', handleReactionRemoved);
      wsClient.off('CHAT_TYPING', handleTyping);
      wsClient.off('PROFILE_UPDATED', handleProfileUpdated);
      wsClient.off('TEAM_MEMBER_UPDATED', handleProfileUpdated);
      wsClient.off('GROUP_LEADER_CHANGED', handleGroupLeaderChanged);
    };
  }, [selectedConvId, user?.id, scrollToBottom, loadConversations, loadColleagues]);

  // Send message
  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!selectedConvId || (!newMessageText.trim() && !pendingAttachment) || isSending) return;
    const content = newMessageText.trim() || (pendingAttachment ? `[${pendingAttachment.file_name}]` : '');
    setIsSending(true);
    try {
      let messageType = 'USER';
      if (pendingAttachment) {
        if (pendingAttachment.mime_type?.startsWith('image/')) messageType = 'IMAGE';
        else if (pendingAttachment.mime_type?.startsWith('video/')) messageType = 'VIDEO';
        else if (pendingAttachment.mime_type?.startsWith('audio/')) messageType = 'AUDIO';
        else messageType = 'DOCUMENT';
      }

      const sent = await apiClient.post<ChatMessage>(`/api/chat/conversations/${selectedConvId}/messages`, {
        content,
        message_type: messageType,
        reply_to_message_id: replyingTo?.id || null,
        attachment_id: pendingAttachment?.id || null,
      });
      setMessages(prev => {
        if (prev.some(m => m.id === sent.id)) return prev;
        return [...prev, sent];
      });
      setNewMessageText('');
      setReplyingTo(null);
      setPendingAttachment(null);
      setTimeout(scrollToBottom, 50);
      apiClient.post(`/api/chat/conversations/${selectedConvId}/typing`, { is_typing: false }).catch(() => {});
    } catch (err: unknown) {
      const e = err as { message?: string };
      toast.error(e?.message || 'Failed to send message');
    } finally {
      setIsSending(false);
    }
  };

  // Media picker trigger
  const handlePickMedia = (type: 'image' | 'video' | 'document' | 'all') => {
    if (!fileInputRef.current) return;
    if (type === 'image') {
      fileInputRef.current.accept = 'image/png,image/jpeg,image/webp,image/gif';
    } else if (type === 'video') {
      fileInputRef.current.accept = 'video/mp4,video/webm,video/quicktime,video/x-matroska';
    } else if (type === 'document') {
      fileInputRef.current.accept = '.pdf,.doc,.docx,.xls,.xlsx,.csv,.zip,.rar,.tar,.gz,.7z,.txt,.json,.yaml,.yml,.xml,.sql,.log,.md,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/plain,text/csv,application/zip';
    } else {
      fileInputRef.current.accept = '*/*';
    }
    fileInputRef.current.click();
  };

  // Unified file upload handler with progress
  const handleUploadFile = async (file: File) => {
    if (!selectedConvId) {
      toast.error('Please select a conversation first');
      return;
    }
    const isImage = file.type.startsWith('image/');
    const isVideo = file.type.startsWith('video/');
    const isAudio = file.type.startsWith('audio/');

    let endpoint = '/api/chat/attachments/document';
    let maxSize = 25 * 1024 * 1024;
    let typeLabel = 'Document';

    if (isImage) {
      endpoint = '/api/chat/attachments/image';
      maxSize = 10 * 1024 * 1024;
      typeLabel = 'Image';
    } else if (isVideo) {
      endpoint = '/api/chat/attachments/video';
      maxSize = 50 * 1024 * 1024;
      typeLabel = 'Video';
    } else if (isAudio) {
      endpoint = '/api/chat/attachments/audio';
      maxSize = 20 * 1024 * 1024;
      typeLabel = 'Audio';
    }

    if (file.size > maxSize) {
      const mb = Math.round(maxSize / (1024 * 1024));
      toast.error(`${typeLabel} must be under ${mb}MB.`);
      return;
    }

    try {
      setIsUploadingAttachment(true);
      setUploadProgress(0);
      const formData = new FormData();
      formData.append('file', file);
      const att = await apiClient.uploadFile<ChatAttachment>(
        endpoint,
        formData,
        (percent) => setUploadProgress(percent)
      );
      setPendingAttachment(att);
      toast.success(`${typeLabel} attached: ${file.name}`);
    } catch (err: unknown) {
      const e = err as { message?: string };
      toast.error(`Failed to upload ${typeLabel.toLowerCase()}: ` + (e?.message || 'Error'));
    } finally {
      setIsUploadingAttachment(false);
      setUploadProgress(0);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUploadFile(file);
  };

  // Drag and drop handlers
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current += 1;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDraggingFile(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current <= 0) {
      setIsDraggingFile(false);
      dragCounterRef.current = 0;
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingFile(false);
    dragCounterRef.current = 0;
    const file = e.dataTransfer.files?.[0];
    if (file) handleUploadFile(file);
  };

  // Voice recording
  const handleStartRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => { if (event.data.size > 0) audioChunksRef.current.push(event.data); };
      recorder.start();
      setIsRecording(true);
      setRecordingDuration(0);
      recordingTimerRef.current = setInterval(() => setRecordingDuration(prev => prev + 1), 1000);
    } catch (err: unknown) {
      const e = err as { message?: string };
      toast.error('Microphone access denied: ' + (e?.message || 'Check permissions'));
    }
  };

  const handleStopRecordingAndSend = async () => {
    if (!mediaRecorderRef.current || !selectedConvId) return;
    const recorder = mediaRecorderRef.current;
    if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
    setIsRecording(false);
    recorder.onstop = async () => {
      const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
      const formData = new FormData();
      formData.append('file', audioBlob, 'voice_message.webm');
      formData.append('duration_seconds', recordingDuration.toString());
      try {
        const att = await apiClient.uploadFile<ChatAttachment>('/api/chat/attachments/audio', formData);
        const sent = await apiClient.post<ChatMessage>(`/api/chat/conversations/${selectedConvId}/messages`, {
          content: 'Voice note', message_type: 'AUDIO', attachment_id: att.id, reply_to_message_id: replyingTo?.id || null
        });
        setMessages(prev => { if (prev.some(m => m.id === sent.id)) return prev; return [...prev, sent]; });
        setReplyingTo(null);
        setTimeout(scrollToBottom, 50);
        toast.success('Voice message sent');
      } catch (err: unknown) {
        const e = err as { message?: string };
        toast.error('Failed to upload voice note: ' + (e?.message || 'Error'));
      }
    };
    recorder.stop();
    recorder.stream.getTracks().forEach(t => t.stop());
  };

  const handleCancelRecording = () => {
    if (mediaRecorderRef.current) {
      if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(t => t.stop());
      setIsRecording(false);
      audioChunksRef.current = [];
    }
  };

  // Reactions
  const handleToggleReaction = async (messageId: string, emoji: string, hasReacted: boolean) => {
    try {
      if (hasReacted) await apiClient.delete(`/api/chat/messages/${messageId}/reactions/${encodeURIComponent(emoji)}`);
      else await apiClient.post(`/api/chat/messages/${messageId}/reactions`, { emoji });
    } catch (err: unknown) {
      const e = err as { message?: string };
      toast.error('Reaction failed: ' + (e?.message || 'Error'));
    }
  };

  // Delete
  const handleDeleteMessage = async (messageId: string) => {
    try {
      const deleted = await apiClient.delete<ChatMessage>(`/api/chat/messages/${messageId}`);
      setMessages(prev => prev.map(m => m.id === messageId ? deleted : m));
      toast.success('Message deleted');
    } catch (err: unknown) {
      const e = err as { message?: string; status?: number };
      if (e?.status === 403 || e?.message?.includes('MESSAGE_DELETE_FORBIDDEN')) {
        toast.error('Permission denied: Only Group Leaders or the author can remove this message.');
      } else {
        toast.error('Delete failed: ' + (e?.message || 'Error'));
      }
    }
  };

  // Moderation
  const handleModerate = async (reason: string) => {
    if (!moderatingMessage) return;
    setIsModerating(true);
    try {
      const deleted = await apiClient.delete<ChatMessage>(`/api/chat/messages/${moderatingMessage.id}`);
      setMessages(prev => prev.map(m => m.id === moderatingMessage.id ? deleted : m));
      toast.success('Message removed and logged in moderation audit');
      setModeratingMessage(null);
    } catch (err: unknown) {
      const e = err as { message?: string };
      toast.error('Moderation failed: ' + (e?.message || 'Error'));
    } finally {
      setIsModerating(false);
    }
  };

  // Direct chat selection (colleague clicked)
  const handleSelectColleague = async (member: TeamMemberBrief) => {
    if (member.role === 'ADMIN' && user?.role === 'EMPLOYEE' && !isLeader) {
      toast.error('Only the active Group Leader can message Admin.');
      return;
    }
    try {
      const conv = await apiClient.post<ConversationItem>('/api/chat/conversations/direct', { other_user_id: member.user_id });
      setConversations(prev => {
        if (!prev.some(c => c.id === conv.id)) return [conv, ...prev];
        return prev;
      });
      setSelectedConvId(conv.id);
      setActiveTab('DIRECT');
    } catch (err: unknown) {
      const e = err as { detail?: { message?: string }; message?: string };
      toast.error(e?.detail?.message || e?.message || 'Could not initiate chat');
    }
  };

  // Typing indicator
  const handleInputChange = (val: string) => {
    setNewMessageText(val);
    if (!selectedConvId) return;
    if (!typingTimeoutRef.current) {
      apiClient.post(`/api/chat/conversations/${selectedConvId}/typing`, { is_typing: true }).catch(() => {});
    } else {
      clearTimeout(typingTimeoutRef.current);
    }
    typingTimeoutRef.current = setTimeout(() => {
      apiClient.post(`/api/chat/conversations/${selectedConvId}/typing`, { is_typing: false }).catch(() => {});
      typingTimeoutRef.current = null;
    }, 2000);
  };

  usePageSearch({
    pageName: 'Chat',
    placeholder: 'Filter conversations...',
    itemCount: conversations.length,
    filteredCount: conversations.length,
    onSearch: () => {},
  });

  const activeConversation = conversations.find(c => c.id === selectedConvId) || myTeam?.conversation;
  const activeTypers = selectedConvId ? (typingUsers[selectedConvId] || []) : [];

  // Dedup messages
  const displayMessages = React.useMemo(() => {
    const seen = new Set<string>();
    return messages.filter((m, idx) => {
      const key = m.id || `m-${idx}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [messages]);

  const getMediaUrl = (url: string) => apiClient.getMediaUrl(url);

  const conversationPlaceholder = activeConversation?.type === 'TEAM'
    ? `Message #${myTeam?.team_name || activeConversation.team_name || 'team'}...`
    : 'Write a message...';

  return (
    <div className="h-[calc(100vh-4rem)] flex bg-[#020817] overflow-hidden">
      {/* Hidden file input */}
      <input type="file" ref={fileInputRef} onChange={handleFileInputChange} className="hidden" />

      {/* LEFT SIDEBAR — hidden on mobile when conversation selected */}
      <div className={`${showMobileSidebar ? 'flex' : 'hidden'} md:flex w-72 flex-shrink-0`}>
        <ChatSidebar
          conversations={conversations}
          colleagues={colleagues}
          activeTab={activeTab}
          selectedConvId={selectedConvId}
          currentUserId={user?.id}
          onTabChange={setActiveTab}
          onSelectConversation={id => setSelectedConvId(id)}
          onSelectColleague={handleSelectColleague}
          getMediaUrl={getMediaUrl}
        />
      </div>

      {/* MAIN CONTENT */}
      <div
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className={`${!showMobileSidebar ? 'flex' : 'hidden'} md:flex flex-1 flex-col overflow-hidden bg-[#071426] relative`}
      >
        {isDraggingFile && (
          <div className="absolute inset-4 z-40 bg-[#071426]/95 border-2 border-dashed border-[#087CFF] rounded-2xl backdrop-blur-md flex flex-col items-center justify-center pointer-events-none animate-in fade-in duration-150 shadow-2xl">
            <UploadCloud className="h-12 w-12 text-[#087CFF] animate-bounce mb-3" />
            <p className="text-base font-semibold text-white">Drop file to share</p>
            <p className="text-xs text-white/50 mt-1">Images (10MB), Videos (50MB), Documents (25MB)</p>
          </div>
        )}

        {activeConversation ? (
          <>
            <ConversationHeader
              conversation={activeConversation}
              myTeam={myTeam}
              onBack={() => setShowMobileSidebar(true)}
              onRefresh={() => selectedConvId && loadMessages(selectedConvId)}
            />
            <MessageList
              messages={displayMessages}
              isLoading={isLoadingMessages}
              currentUserId={user?.id}
              isLeader={isLeader}
              highlightedMessageId={highlightedMessageId}
              messagesEndRef={messagesEndRef}
              getMediaUrl={getMediaUrl}
              onReply={msg => { setReplyingTo(msg); composerInputRef.current?.focus(); }}
              onDelete={handleDeleteMessage}
              onModerate={msg => setModeratingMessage(msg)}
              onToggleReaction={handleToggleReaction}
              onScrollToMessage={scrollToMessage}
              onOpenProfile={openProfileDrawer}
            />
            <TypingIndicator names={activeTypers} />
            {replyingTo && <ReplyBar message={replyingTo} onCancel={() => setReplyingTo(null)} />}
            {isRecording ? (
              <VoiceRecorder duration={recordingDuration} onCancel={handleCancelRecording} onSend={handleStopRecordingAndSend} />
            ) : (
              <MessageComposer
                value={newMessageText}
                onChange={handleInputChange}
                onSubmit={handleSendMessage}
                onPickMedia={handlePickMedia}
                onPasteFile={handleUploadFile}
                onStartRecording={handleStartRecording}
                isSending={isSending}
                isUploadingAttachment={isUploadingAttachment}
                uploadProgress={uploadProgress}
                pendingAttachment={pendingAttachment}
                onClearAttachment={() => setPendingAttachment(null)}
                placeholder={conversationPlaceholder}
                inputRef={composerInputRef}
              />
            )}
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center">
            <EmptyChatState tab={activeTab} />
          </div>
        )}
      </div>

      {/* Profile Drawer */}
      {profileDrawerUser && (
        <ProfileDrawer
          member={profileDrawerUser}
          open={profileDrawerOpen}
          onClose={closeProfileDrawer}
          onMessage={handleSelectColleague}
          getMediaUrl={getMediaUrl}
        />
      )}

      {/* Moderation Modal */}
      {moderatingMessage && (
        <ModerationModal
          message={moderatingMessage}
          onConfirm={handleModerate}
          onCancel={() => setModeratingMessage(null)}
        />
      )}
    </div>
  );
}
