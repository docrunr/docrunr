import { useCallback, useEffect, useRef, useState } from 'react';
import { uploadDocuments } from '../../../services/workerApi';
import type { WorkerMode } from '../../../services/workerApi.types';
import type { SelectedUploadFile } from '../types';

export function useDocumentUpload(mode: WorkerMode) {
  const [queue, setQueue] = useState<SelectedUploadFile[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [batchTotal, setBatchTotal] = useState(0);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [successCount, setSuccessCount] = useState(0);
  const [failCount, setFailCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [llmProfile, setLlmProfile] = useState<string>('');

  const queueRef = useRef(queue);
  const processingRef = useRef(false);
  const llmProfileRef = useRef(llmProfile);

  useEffect(() => {
    queueRef.current = queue;
  }, [queue]);

  useEffect(() => {
    llmProfileRef.current = llmProfile;
  }, [llmProfile]);

  useEffect(() => {
    if (mode !== 'llm') {
      setLlmProfile('');
    }
  }, [mode]);

  const addFiles = useCallback((list: File[]) => {
    if (!list.length) {
      return;
    }
    setError(null);
    setSuccessCount(0);
    setFailCount(0);
    setQueue((prev) => [...prev, ...list.map((file) => ({ id: crypto.randomUUID(), file }))]);
  }, []);

  const removeFile = useCallback((id: string) => {
    setQueue((prev) => prev.filter((p) => p.id !== id));
  }, []);

  const clearQueue = useCallback(() => {
    setQueue([]);
  }, []);

  const reset = useCallback(() => {
    setQueue([]);
    setIsProcessing(false);
    processingRef.current = false;
    setBatchTotal(0);
    setCurrentIndex(0);
    setSuccessCount(0);
    setFailCount(0);
    setError(null);
  }, []);

  const submit = useCallback(async () => {
    if (processingRef.current) {
      return;
    }
    const snapshot = [...queueRef.current];
    if (!snapshot.length) {
      return;
    }

    processingRef.current = true;
    setIsProcessing(true);
    setError(null);
    setBatchTotal(snapshot.length);
    setSuccessCount(0);
    setFailCount(0);

    const profile = mode === 'llm' ? llmProfileRef.current : '';
    const opts = profile ? { llmProfile: profile } : undefined;

    for (let i = 0; i < snapshot.length; i++) {
      const item = snapshot[i];
      setCurrentIndex(i + 1);

      try {
        const res = await uploadDocuments([item.file], opts);
        const row = res.items[0];
        setQueue((q) => q.filter((p) => p.id !== item.id));

        if (row?.status === 'queued') {
          setSuccessCount((c) => c + 1);
        } else {
          setFailCount((c) => c + 1);
        }
      } catch (e) {
        setQueue((q) => q.filter((p) => p.id !== item.id));
        setFailCount((c) => c + 1);
        setError(e instanceof Error ? e.message : 'Unknown error');
      }
    }

    setIsProcessing(false);
    processingRef.current = false;
    setBatchTotal(0);
    setCurrentIndex(0);
  }, [mode]);

  return {
    queue,
    isProcessing,
    batchTotal,
    currentIndex,
    successCount,
    failCount,
    error,
    llmProfile,
    setLlmProfile,
    addFiles,
    removeFile,
    clearQueue,
    reset,
    submit,
  };
}
