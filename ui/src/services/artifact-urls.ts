import { workerApiUrl } from './workerApi';

export function artifactUrl(path: string): string {
  return workerApiUrl('/artifact', { path });
}
