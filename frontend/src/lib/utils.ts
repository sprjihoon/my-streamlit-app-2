import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

// tailwind-merge 3 treats `prefix` as a `name:` modifier, not Tailwind's `tw-` class prefix.
const twMerge = extendTailwindMerge({
  experimentalParseClassName({ className, parseClassName }) {
    return parseClassName(className.replace(/(^|:)(!?)tw-/g, '$1$2'));
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
