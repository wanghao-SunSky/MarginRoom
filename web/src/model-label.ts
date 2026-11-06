/** Product name only: runtime reasoning settings belong in model configuration. */
export function readerModelLabel(status:{model?:string,model_label?:string}):string {
 if(status.model==='deepseek-flash')return 'DeepSeek Flash';
 return (status.model_label||status.model||'').split(' · ')[0];
}
