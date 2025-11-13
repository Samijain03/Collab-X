# chatapp/gemini_utils.py

import google.generativeai as genai
from django.conf import settings

# Configure the API client
if settings.GOOGLE_GEMINI_API_KEY:
    genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)
else:
    print("WARNING: GOOGLE_GEMINI_API_KEY not set. Bot features will be disabled.")

def format_chat_history(messages_queryset):
    """
    Converts a queryset of Message or GroupMessage objects into a
    plain text string for the AI prompt.
    
    --- NEW ---
    Includes the message ID in the format [id:MSG_ID]
    """
    history = []
    for msg in messages_queryset:
        if not msg.is_deleted:
            # Get the display name or username
            sender_name = msg.sender.profile.display_name or msg.sender.username
            # --- UPDATED LINE ---
            history.append(f"[id:{msg.id}] {sender_name}: {msg.content}")
    
    return "\n".join(history)

def get_collab_response(chat_history_string, user_query):
    """
    Sends the formatted chat history and a user query to the Gemini API
    with the 'Collab-X' personality.
    """
    if not settings.GOOGLE_GEMINI_API_KEY:
         return "Sorry, the bot is not configured. (Missing API Key)"
         
    # Use a fast model
    model = genai.GenerativeModel('gemini-2.5-flash')

    # --- UPDATED "Personality" Prompt ---
    prompt = f"""
    You are 'Collab-X', a helpful AI assistant integrated into this chat application.
    Your personality is helpful, concise, and professional.
    You are part of the Collab-X application.
    
    A user has asked for your help regarding their chat history.
    The user's specific request is: "{user_query}"
    
    The chat history you are analyzing is formatted as: [id:MESSAGE_ID] Sender: Message
    
    --- TASK ---
    1.  Analyze the chat history below to answer the user's request.
    2.  If your answer refers to a specific, single message (e.g., "you mentioned X here"),
        find the *most relevant* MESSAGE_ID for that reference.
    3.  After you write your answer, append a special tag: [jump_to: ID]
        (e.g., "I found the message where you discussed the deadline." [jump_to: 142])
    4.  ONLY add the [jump_to: ID] tag if you are referencing ONE specific message.
    5.  If it's a general summary (e.g., "you talked about two things..."), DO NOT add the tag.
    
    --- CHAT HISTORY START ---
    {chat_history_string}
    --- CHAT HISTORY END ---
    
    Your Answer:
    """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return "Sorry, I had trouble processing that request. Please try again."