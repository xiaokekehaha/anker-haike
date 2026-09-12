/** 票 29：前端图片处理。长边压缩到 1600 px，超过 5 MB 或非图片在 Composer 内联提示，不进入对话流（04 §1、05 §6）。 */

export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
export const MAX_EDGE_PX = 1600;
export type ImagePurpose = 'fault' | 'receipt';

export type ImageCheck = { ok: true } | { ok: false; code: 'too_large' | 'unsupported_type'; message: string };

export function checkImage(file: { size: number; type: string }): ImageCheck {
  if (!file.type.startsWith('image/')) {
    return { ok: false, code: 'unsupported_type', message: `不支持的文件类型：${file.type || '未知'}，请选择图片。` };
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return {
      ok: false,
      code: 'too_large',
      message: `图片 ${(file.size / 1024 / 1024).toFixed(1)} MB 超过 5 MB 上限，压缩后仍过大，请换一张。`,
    };
  }
  return { ok: true };
}

/** 有 canvas 能力时把长边压到 1600 px 并转 JPEG；测试环境（jsdom）或解码失败时原样返回。 */
export async function compressImage(file: File, maxEdge = MAX_EDGE_PX): Promise<File> {
  if (typeof createImageBitmap !== 'function' || typeof document === 'undefined') return file;
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && file.size <= MAX_IMAGE_BYTES) return file;
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext('2d');
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.86));
    if (!blob) return file;
    return new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' });
  } catch {
    return file;
  }
}

/** 压缩后再校验；返回可发送的文件或拒绝原因。 */
export async function prepareImage(file: File): Promise<{ file: File } | { error: string }> {
  const pre = checkImage(file);
  if (!pre.ok && pre.code === 'unsupported_type') return { error: pre.message };
  const compressed = await compressImage(file);
  const post = checkImage(compressed);
  return post.ok ? { file: compressed } : { error: post.message };
}

export function imageUrl(sessionId: string, imageId: string): string {
  return `/sessions/${encodeURIComponent(sessionId)}/images/${encodeURIComponent(imageId)}`;
}
