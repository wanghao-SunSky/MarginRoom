/** A captured quote may outlive focus; a selection toolbar must not. */
export function selectedReadingText(root:Pick<Node,'contains'>|null, selection:Pick<Selection,'anchorNode'|'focusNode'|'isCollapsed'|'toString'>|null):string {
 if(!root||!selection||selection.isCollapsed||!root.contains(selection.anchorNode)||!root.contains(selection.focusNode))return '';
 return selection.toString().trim().slice(0,5000);
}
