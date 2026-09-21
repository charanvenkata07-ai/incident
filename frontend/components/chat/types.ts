export type ConversationTabType = 'TEAM' | 'DIRECT';

export interface ChatMember {
  id: string;
  user_id: string;
  name: string;
  email: string;
  role: string;
  avatar_url?: string;
  last_read_at?: string;
}

export interface ChatAttachment {
  id: string;
  file_name: string;
  mime_type: string;
  file_size: number;
  url: string;
  width?: number;
  height?: number;
  duration_seconds?: number;
  status: string;
}

export interface ReactionCount {
  emoji: string;
  count: number;
  users: string[];
}

export interface ReplyToPreview {
  id: string;
  sender_name: string;
  sender_id?: string;
  content: string;
  message_type: string;
  is_deleted: boolean;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  sender_id?: string;
  sender_name: string;
  sender_role: string;
  sender_email?: string;
  sender_avatar_url?: string;
  content: string;
  message_type: string;
  incident_id?: string;
  incident_number?: string;
  reply_to_message_id?: string;
  reply_to?: ReplyToPreview;
  attachment_id?: string;
  attachment?: ChatAttachment;
  reactions: ReactionCount[];
  user_reactions: string[];
  client_message_id?: string;
  is_edited: boolean;
  is_deleted: boolean;
  deleted_by?: string;
  delete_reason?: string;
  edited_at?: string;
  deleted_at?: string;
  created_at: string;
}

export interface ConversationItem {
  id: string;
  type: 'TEAM' | 'DIRECT' | 'INCIDENT' | 'ADMIN_TEAM';
  team_id?: string;
  team_name?: string;
  incident_id?: string;
  incident_number?: string;
  title?: string;
  members: ChatMember[];
  last_message?: ChatMessage;
  unread_count: number;
  created_at: string;
  updated_at?: string;
}

export interface TeamMemberBrief {
  user_id: string;
  employee_id: string;
  full_name: string;
  email: string;
  role: string;
  avatar_url?: string;
  is_present: boolean;
  is_group_leader?: boolean;
  availability_status: string;
  on_shift: boolean;
  current_shift_name?: string;
  phone?: string;
  bio?: string;
  timezone?: string;
}

export interface MyTeamChatData {
  team_id: string;
  team_name: string;
  team_description?: string;
  conversation_id: string;
  member_count: number;
  present_count: number;
  active_shift_name?: string;
  members: TeamMemberBrief[];
  conversation: ConversationItem;
}

export const EMOJI_REACTIONS = ['❤️', '😂', '👍', '👏', '🔥', '😮', '😢', '🙏', '😍', '🎉'] as const;
