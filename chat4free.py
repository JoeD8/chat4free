#imports
from fastapi_poe import make_app
from modal import Image, Stub, asgi_app

from typing import AsyncIterable
import re

from fastapi_poe import PoeBot
from fastapi_poe.client import stream_request
from fastapi_poe.types import PartialResponse, ProtocolMessage, QueryRequest, SettingsRequest, SettingsResponse

#classes
class BotDefinitions(PoeBot):

    async def get_response(
        self, request: QueryRequest
    ) -> AsyncIterable[PartialResponse]:

        #default settings
        chatbot = "solar-mini"
        memory = ""
        
        #separate commands from prompts
        commands: List[str] = []
        for chat in request.query:
            command = ""
            if chat.content.startswith("["):
                closebracket = chat.content.find("]")
                if closebracket < 1:
                    command = chat.content[1:].strip().lower()
                    chat.content = ""
                else:
                    command = chat.content[1:closebracket].strip().lower()
                    chat.content = chat.content[closebracket+1:].strip()

                if "solar" in command: chatbot = "solar-mini"
                if "mixtral" in command: chatbot = "mixtral-8x7b-groq"
                if "groq" in command: chatbot = "llama-2-70b-groq"
                if "claude" in command: chatbot = "claude-instant"
                if "c100" in command: chatbot = "claude-instant-100k"
                if "chatgpt" in command: chatbot = "chatgpt"
                if "haiku" in command: chatbot = "claude-3-haiku"
                if "haiku200k" in command: chatbot = "claude-3-haiku-200k"
                if "sonnet" in command: chatbot = "claude-3-sonnet"
                if "medium" in command: chatbot = "mistral-medium"

                if "bot" in command: chat.role = "bot"
                if "system" in command:
                    if len(commands) == 0:
                        chat.role = "system"
                    else:
                        chat.role = "bot"
                if "remember" in command:
                    memory = chat.content
                    chat.content = ""

            commands.append(command)

        #remove blank chat entries
        newchat: List[ProtocolMessage] = []
        for chat in request.query:
            if chat.content.strip() != "":
                newchat.append(chat)
        request.query = newchat

        #generate response
        if request.query[-1].content == "" or request.query[-1].role != "user":
            yield PartialResponse(text = f"[{chatbot}] ")
        else:
            #add memory to the user message before the last one
            if len(memory) > 0:
                index = 0
                for chat in reversed(request.query):
                    if index > 0 and chat.role == "user":
                        chat.content = f"{chat.content} [remember: {memory}]"
                        break
                    index += 1
            #stream bot response
            replace = True
            async for msg in stream_request(request, chatbot, request.access_key):
                yield PartialResponse(text = msg.text, is_replace_response = replace)
                if msg.text != "" :
                    replace = False
            
    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:

        #details about your bot
        return SettingsResponse(
            #this can list a max of 10, even if the bot only ever calls one or two
            server_bot_dependencies={
                "solar-mini":1,        
                "mixtral-8x7b-groq":1, 
                "llama-2-70b-groq":1,  
                "claude-instant":1,    
                "claude-instant-100k":1,
                "chatgpt":1,            
                "claude-3-haiku":1,     
                "claude-3-haiku-200k":1,
                "claude-3-sonnet":1,    
                "mistral-medium":1,      
            },
            #introduction_message="",
        )

#Execute
bot = BotDefinitions()
image = Image.debian_slim().pip_install_from_requirements("requirements.txt")
stub = Stub("chat4free")
@stub.function(image=image)
@asgi_app()
def fastapi_app():
    app = make_app(bot, access_key="---comes from bot settings page---")
    return app
