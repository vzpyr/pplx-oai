from flask import Flask, request, jsonify, Response
import json
import sys
import os
import re
import ast

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'perplexity-ai'))
import perplexity

app = Flask(__name__)

MODELS_MAP = {
    'auto': ['perplexity-auto'],
    'pro': ['perplexity-pro', 'sonar', 'gpt-5.2', 'claude-4.5-sonnet', 'grok-4-1'],
    'reasoning': ['perplexity-reasoning', 'gpt-5.2-thinking', 'claude-4.5-sonnet-thinking', 'gemini-3.0-pro', 'kimi-k2-thinking', 'grok-4.1-reasoning'],
    'deep research': ['perplexity-deep-research']
}

REVERSE_MODEL_MAP = {}
for mode, models in MODELS_MAP.items():
    for model in models:
        REVERSE_MODEL_MAP[model] = (mode, None if model.startswith('perplexity-') else model)

DEFAULT_MODEL = 'perplexity-auto'

_cached_client = None
_cached_cookies = None

def load_cookies():
    try:
        with open('cookies.txt', 'r') as f:
            content = f.read()
            match = re.search(r'cookies\s*=\s*(\{.*\})', content, re.DOTALL)
            if match:
                cookies_dict = ast.literal_eval(match.group(1))
                if isinstance(cookies_dict, dict):
                    return cookies_dict
            return None
    except FileNotFoundError:
        return None
    except (ValueError, SyntaxError) as e:
        print(f"Error parsing cookies.txt: {e}")
        return None
    except Exception as e:
        print(f"Error loading cookies: {e}")
        return None

def get_client():
    global _cached_client, _cached_cookies
    if _cached_client is None:
        _cached_cookies = load_cookies()
        if _cached_cookies:
            _cached_client = perplexity.Client(_cached_cookies)
        else:
            _cached_client = perplexity.Client()
    return _cached_client

def fix_citation_format(content):
    lines = content.split('\n')
    in_sources = False
    before_sources = []
    sources = []
    
    for line in lines:
        if '# Sources' in line:
            in_sources = True
            before_sources.append(line)
            continue
        
        if in_sources:
            match = re.search(r'(https://[^ ]+)\[(\d+)\]', line)
            if match:
                url = match.group(1)
                num = match.group(2)
                sources.append((int(num), url))
                continue
            match = re.search(r'\[(\d+)\]\s*(https://\S+)', line)
            if match:
                num = match.group(1)
                url = match.group(2)
                sources.append((int(num), url))
                continue
            if re.match(r'^https://', line.strip()):
                continue
        else:
            before_sources.append(line)
    
    sources.sort(key=lambda x: x[0])
    sources_section = '\n'.join(f'[{num}] {url}' for num, url in sources)
    
    print(f"[DEBUG] Fixed and sorted {len(sources)} citations")
    
    return '\n'.join(before_sources) + '\n' + sources_section if sources else '\n'.join(before_sources)

def parse_source_from_last_message(last_message):
    match = re.search(r'/sources:([\w,]+)', last_message, re.IGNORECASE)
    if match:
        sources_str = match.group(1).lower()
        sources_list = [s.strip() for s in sources_str.split(',')]
        source_map = {
            'web': 'web',
            'social': 'social',
            'scholar': 'scholar',
            'academic': 'scholar'
        }
        sources = [source_map.get(s, 'web') for s in sources_list]
        return sources, match.group(0)
    return ['web'], None

def parse_messages(messages):
    query = ""
    files = {}
    conversation_parts = []
    
    for msg in messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if part.get('type') == 'text':
                    text_parts.append(part.get('text', ''))
                elif part.get('type') == 'file':
                    file_data = part.get('file')
                    if file_data:
                        filename = part.get('file_name', f'file_{len(files)}')
                        files[filename] = file_data
            content = ' '.join(text_parts)
        
        conversation_parts.append(f"{role.title()}: {content}")
    
    if conversation_parts:
        if len(conversation_parts) == 1:
            query = conversation_parts[0]
        else:
            query = "Here is our conversation history:\n\n" + "\n".join(conversation_parts[:-1]) + f"\n\n{conversation_parts[-1]}"
    
    citation_instruction = "\n\nAt the end, list sources under '# Sources' with citation numbers like [1], [2], [3]."
    query += citation_instruction
    
    return query, files

@app.route('/v1/models', methods=['GET'])
def list_models():
    try:
        cookies = load_cookies()
        
        if cookies:
            return jsonify({
                'object': 'list',
                'data': [
                    {
                        'id': model,
                        'object': 'model',
                        'created': 1677610602,
                        'owned_by': 'perplexity'
                    }
                    for models in MODELS_MAP.values()
                    for model in models
                ]
            })
        else:
            return jsonify({
                'object': 'list',
                'data': [{
                    'id': 'perplexity-auto',
                    'object': 'model',
                    'created': 1677610602,
                    'owned_by': 'perplexity'
                }]
            })
    except Exception as e:
        print(f"Error listing models: {e}")
        return jsonify({'error': {'message': str(e), 'type': 'api_error'}}), 500

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': {'message': 'Invalid JSON', 'type': 'invalid_request_error'}}), 400
        
        messages = data.get('messages', [])
        model = data.get('model', DEFAULT_MODEL)
        stream = data.get('stream', True)
        
        if not messages:
            return jsonify({'error': {'message': 'No messages provided', 'type': 'invalid_request_error'}}), 400
        
        mode, perplexity_model = REVERSE_MODEL_MAP.get(model, ('auto', None))
        
        query, files = parse_messages(messages)
        
        if not query:
            return jsonify({'error': {'message': 'No query provided', 'type': 'invalid_request_error'}}), 400
        
        print(f"[DEBUG] Processing chat completion request with model: {model}, mode: {mode}")
        
        sources, source_text = parse_source_from_last_message(query)
        if source_text:
            query = query.replace(source_text, '')
            print(f"[DEBUG] Found source specification: {source_text}")
        print(f"[DEBUG] Using sources: {sources}")
        
        response = get_client().search(
            query,
            mode=mode,
            model=perplexity_model,
            sources=sources,
            files=files,
            stream=False,
            language='en-US',
            incognito=True
        )
        
        content = response.get('answer', '') if response else ''
        content = fix_citation_format(content)
        
        print(f"[DEBUG] Request completed successfully, returning response")
        
        query_tokens = len(query.split())
        content_tokens = len(content.split())
        
        chat_id = f'chatcmpl-{hash(query) % 1000000009}'
        
        if stream:
            def generate():
                yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': 1677610602, 'model': model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
                if content:
                    yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': 1677610602, 'model': model, 'choices': [{'index': 0, 'delta': {'content': content}, 'finish_reason': None}]})}\n\n"
                yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': 1677610602, 'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                yield "data: [DONE]\n\n"
            
            return Response(generate(), mimetype='text/event-stream')
        else:
            return jsonify({
                'id': chat_id,
                'object': 'chat.completion',
                'created': 1677610602,
                'model': model,
                'choices': [{
                    'index': 0,
                    'message': {'role': 'assistant', 'content': content},
                    'finish_reason': 'stop'
                }],
                'usage': {
                    'prompt_tokens': query_tokens,
                    'completion_tokens': content_tokens,
                    'total_tokens': query_tokens + content_tokens
                }
            })
    except Exception as e:
        print(f"Error in chat completion: {e}")
        return jsonify({'error': {'message': str(e), 'type': 'api_error'}}), 500

@app.route('/', methods=['GET'])
def home():
    return 'pplx-oai is running'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)