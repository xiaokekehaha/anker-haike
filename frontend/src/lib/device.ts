/** 输入设备判定：桌面端（有精确指针）回车直接发送，触屏端回车仍是换行，发送交给按钮。 */

export const TOUCH_PRIMARY_QUERY = '(hover: none) and (pointer: coarse)';

/** 手机 / 平板等以触屏为主的设备返回 true；无法判定时按桌面处理。 */
export function isTouchPrimary(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  try { return window.matchMedia(TOUCH_PRIMARY_QUERY).matches; } catch { return false; }
}

/** 从剪贴板事件里取出图片文件；浏览器差异：多数给 files，Safari 只给 items。 */
export function clipboardImages(data: DataTransfer | null): File[] {
  if (!data) return [];
  const files = Array.from(data.files ?? []).filter(file => file.type.startsWith('image/'));
  if (files.length) return files;
  for (const item of Array.from(data.items ?? [])) {
    if (item.kind !== 'file' || !item.type.startsWith('image/')) continue;
    const file = item.getAsFile();
    if (file) files.push(file);
  }
  return files;
}
