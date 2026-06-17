// Module augmentation (this file is a module thanks to the import) adding the non-standard
// directory-upload attribute to React's input props.
import 'react';

declare module 'react' {
  interface InputHTMLAttributes<T> {
    webkitdirectory?: string;
  }
}
