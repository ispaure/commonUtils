"""Transient literal search in rendered Markdown, independent of storage/host policy."""
import asyncio
import json
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .event_loop import DebouncedCallback
from .presentation import navigation_button

# Host-evaluated only: document scripts stay disabled by the renderer's CSP.
# Ranges preserve authored DOM, links, selection and speech's separate marks.
_SEARCH_JS = r'''(function(options){
const key='__commonutilsMarkdownSearch';
let state=window[key];
if(!state){
 state=window[key]={library:[],page:[],index:-1,query:'',overlay:null};
 state.paint=function(){
   if(state.overlay)state.overlay.remove();
   state.overlay=null;
   if(!state.page.length && !state.library.length){
     if(window.CSS && CSS.highlights)for(const name of ['library','page','current'])CSS.highlights.delete('commonutils-'+name);
     return;
   }
   if(window.CSS && CSS.highlights && window.Highlight){
     if(!document.getElementById('commonutils-search-style')){
       const style=document.createElement('style'); style.id='commonutils-search-style';
       style.textContent='::highlight(commonutils-library){background:#ffedaa;color:#171717}'+
         '::highlight(commonutils-page){background:#ffe082;color:#171717}'+
         '::highlight(commonutils-current){background:#ffa726;color:#171717}';
       document.head.appendChild(style);
     }
     for(const name of ['library','page'])CSS.highlights.set('commonutils-'+name,new Highlight(...state[name]));
     CSS.highlights.set('commonutils-current',new Highlight(...(state.index>=0?[state.page[state.index]]:[])));
   }else{
     if(window.CSS && CSS.highlights)for(const name of ['library','page','current'])CSS.highlights.delete('commonutils-'+name);
     // Older WebViews: empty, pointer-transparent rectangles; never wrap/split text.
     const layer=document.createElement('div');layer.dataset.nativeSearchOverlay='true';
     layer.style.cssText='position:fixed;left:0;top:0;width:0;height:0;pointer-events:none;z-index:2147483000';
     const height=window.innerHeight,width=window.innerWidth;
     for(const name of ['library','page'])for(let i=0;i<state[name].length;i++){
       for(const rect of state[name][i].getClientRects()){
         if(rect.bottom<0 || rect.top>height || rect.right<0 || rect.left>width)continue;
         const box=document.createElement('div');
         box.style.cssText='position:absolute;pointer-events:none;background:'+
           (name==='page' && i===state.index?'rgba(255,152,0,.55)':'rgba(255,210,70,.35)')+
           ';left:'+rect.left+'px;top:'+rect.top+'px;width:'+rect.width+'px;height:'+rect.height+'px';
         layer.appendChild(box);
       }
     }
     document.body.appendChild(layer);state.overlay=layer;
   }
 };
 window.addEventListener('scroll',()=>state.paint(),{passive:true});
 window.addEventListener('resize',()=>state.paint(),{passive:true});
}
if(!options.page && !options.library){
 state.library=[];state.page=[];state.index=-1;state.query='';state.paint();
 return JSON.stringify({count:0,index:-1,limited:false});
}
const entries=[];let text='',previous=null;
const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,{acceptNode(node){
 const parent=node.parentElement;
 return !parent || parent.closest('script,style,noscript,[data-native-search-overlay]') || !parent.getClientRects().length || ['hidden','collapse'].includes(getComputedStyle(parent).visibility) ? NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT;
}});
while(walker.nextNode()){
 const node=walker.currentNode,block=node.parentElement.closest('p,h1,h2,h3,h4,h5,h6,li,pre,td,th,div,blockquote,body');
 if(previous && previous!==block)text+='\n';
 entries.push({node,start:text.length,end:text.length+node.length});text+=node.data;previous=block;
}
function matches(query){
 if(!query)return [];
 const pattern=new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'gi');
 const ranges=[];let match,first=0,last=0;
 while((match=pattern.exec(text)) && ranges.length<5000){
   const end=match.index+match[0].length;
   while(first<entries.length && entries[first].end<=match.index)first++;
   last=Math.max(last,first);
   while(last<entries.length && entries[last].end<end)last++;
   if(first>=entries.length || last>=entries.length)break;
   const range=document.createRange();range.setStart(entries[first].node,match.index-entries[first].start);
   range.setEnd(entries[last].node,end-entries[last].start);ranges.push(range);
 }
 return ranges;
}
const same=state.query===options.page,oldIndex=state.index;
state.library=matches(options.library);state.page=matches(options.page);state.query=options.page;
state.index=state.page.length ? (same?Math.min(Math.max(oldIndex,0),state.page.length-1):0):-1;
if(options.step && state.page.length){
 if(same && oldIndex>=0)state.index=(state.index+options.step+state.page.length)%state.page.length;
 else if(options.step<0)state.index=state.page.length-1;
}
const current=state.page[state.index];
const reveal=options.reveal ? (current || state.library[0]):null;
if(reveal){
 const rect=reveal.getBoundingClientRect();
 window.scrollBy(0,rect.top-window.innerHeight/3);
}
state.paint();
return JSON.stringify({count:state.page.length,index:state.index,limited:state.page.length===5000});
})(OPTIONS)'''


def search_script(page='', library='', *, step=0, reveal=False):
    return _SEARCH_JS.replace('OPTIONS', json.dumps(dict(page=page, library=library, step=step, reveal=reveal)))


class MarkdownPageSearch:
    """Two-row phone-friendly Find; hosts call loading()/loaded() around set_content."""
    def __init__(self, web, container, *, insertion_index=0, valid=lambda: True):
        self.web, self.container, self.insertion_index = web, container, insertion_index
        self.valid = valid
        self.library_query = ''
        self.ready = False
        self.closed = False
        self.revision = 0
        self.lock = asyncio.Lock()
        self.debounce = DebouncedCallback(lambda *a, **kw: self.request(reveal=True))
        self.query = toga.TextInput(placeholder='Find in this page', on_change=self.debounce, style=Pack(flex=1, height=48))
        self.notice = toga.Label('This page', style=Pack(flex=1, font_size=12))
        self.previous_button = navigation_button('back', 'Previous match', on_press=lambda w: self.request(step=-1, reveal=True), enabled=False)
        self.next_button = navigation_button('forward', 'Next match', on_press=lambda w: self.request(step=1, reveal=True), enabled=False)
        self.box = toga.Box(children=[
            toga.Box(children=[self.query, toga.Button('Done', on_press=self.hide, style=Pack(height=48))], style=Pack(direction=ROW)),
            toga.Box(children=[self.previous_button, self.notice, self.next_button], style=Pack(direction=ROW))],
            style=Pack(direction=COLUMN))
        self.button = navigation_button('find', 'Find in this page', on_press=self.show)
        self.button.accessible_name = 'Find in this page'
        self.query.accessible_name = 'Find in this page'

    @property
    def visible(self):
        return self.box in self.container.children

    def show(self, widget=None, **kwargs):
        if self.closed or not self.valid():
            return
        if not self.visible:
            self.container.insert(self.insertion_index, self.box)
        self.query.focus()
        self.request(reveal=True)

    def hide(self, widget=None, **kwargs):
        self.debounce.cancel()
        if self.visible:
            self.container.remove(self.box)
        self.request()

    def loading(self):
        self.ready = False
        self.revision += 1
        self.notice.text = 'This page · loading…'
        self.previous_button.enabled = self.next_button.enabled = False

    def loaded(self, widget=None, *, reveal=True, **kwargs):
        if self.closed:
            return
        self.ready = True
        self.request(reveal=reveal)

    def set_library_query(self, query):
        self.library_query = query.strip()
        self.request()

    def request(self, *, step=0, reveal=False):
        if self.closed or not self.ready or not self.valid():
            return
        return asyncio.get_event_loop().create_task(self.update(step=step, reveal=reveal, revision=self.revision))

    async def update(self, *, step=0, reveal=False, revision=None):
        revision = self.revision if revision is None else revision
        async with self.lock:
            if self.closed or not self.ready or revision != self.revision or not self.valid():
                return
            page = (self.query.value or '') if self.visible else ''
            library = self.library_query
            try:
                result = await self.web.evaluate_javascript(search_script(page, library, step=step, reveal=reveal))
            except Exception:
                if not self.closed and self.ready and revision == self.revision and self.valid():
                    self.notice.text = 'This page · search unavailable'
                    self.previous_button.enabled = self.next_button.enabled = False
                return
            if (self.closed or not self.ready or revision != self.revision or not self.valid()
                    or page != ((self.query.value or '') if self.visible else '') or library != self.library_query):
                return
            if not isinstance(result, str):  # Toga dummy backends have no JS engine.
                return
            result = json.loads(result)
            count, index = result['count'], result['index']
            self.previous_button.enabled = self.next_button.enabled = bool(count)
            self.notice.text = ('This page · ' + (f'{index + 1} of {count}' + ('+' if result['limited'] else '')
                if count else 'No matches')) if page else 'This page · enter text to find'

    def dispose(self):
        self.closed = True
        self.revision += 1
        self.debounce.cancel()
        if self.visible:
            self.container.remove(self.box)
        self.library_query = ''
        self.query.value = ''
        self.debounce.cancel()
