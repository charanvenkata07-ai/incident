"""
Clean and consolidate duplicate TEAM conversations in IncidentFlow database.
Merges members and messages to the oldest canonical conversation, then removes orphans.
"""
import asyncio
from sqlalchemy import select, func, text, update, delete
from app.core.database import async_session_maker
from app.models.conversation import Conversation, ConversationMember, ChatMessage

async def clean_duplicate_team_conversations():
    async with async_session_maker() as session:
        stmt = (
            select(Conversation.team_id)
            .where(Conversation.type == 'TEAM', Conversation.team_id.isnot(None))
            .group_by(Conversation.team_id)
            .having(func.count(Conversation.id) > 1)
        )
        res = await session.execute(stmt)
        team_ids = res.scalars().all()
        print(f'Found {len(team_ids)} teams with duplicate TEAM conversations.')

        for tid in team_ids:
            convs_stmt = (
                select(Conversation)
                .where(Conversation.type == 'TEAM', Conversation.team_id == tid)
                .order_by(Conversation.created_at.asc())
            )
            convs_res = await session.execute(convs_stmt)
            convs = convs_res.scalars().all()
            if len(convs) < 2:
                continue

            canonical = convs[0]
            duplicates = convs[1:]
            print(f'Team {tid}: Canonical conversation is {canonical.id}, consolidating {len(duplicates)} duplicate(s).')

            for dup in duplicates:
                await session.execute(
                    update(ChatMessage)
                    .where(ChatMessage.conversation_id == dup.id)
                    .values(conversation_id=canonical.id)
                )

                dup_members_res = await session.execute(
                    select(ConversationMember.user_id).where(ConversationMember.conversation_id == dup.id)
                )
                dup_uids = dup_members_res.scalars().all()
                for uid in dup_uids:
                    canon_mem = await session.execute(
                        select(ConversationMember).where(
                            ConversationMember.conversation_id == canonical.id,
                            ConversationMember.user_id == uid
                        )
                    )
                    if not canon_mem.scalar_one_or_none():
                        session.add(ConversationMember(conversation_id=canonical.id, user_id=uid))

                await session.execute(
                    delete(ConversationMember).where(ConversationMember.conversation_id == dup.id)
                )
                await session.execute(
                    delete(Conversation).where(Conversation.id == dup.id)
                )

            await session.commit()
            print(f'Team {tid} consolidation completed.')

        print('All duplicate TEAM conversations successfully consolidated.')

if __name__ == '__main__':
    asyncio.run(clean_duplicate_team_conversations())
