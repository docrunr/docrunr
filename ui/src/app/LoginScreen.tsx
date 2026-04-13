import { Button, Center, Paper, PasswordInput, Stack, Text, Title } from '@mantine/core';
import { type SubmitEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useWorkerAuth } from './useWorkerAuth';

export function LoginScreen() {
  const { t } = useTranslation();
  const { login } = useWorkerAuth();
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    void (async () => {
      try {
        await login(password);
      } catch (e) {
        const code = e instanceof Error ? e.message : '';
        if (code === 'invalid_password') {
          setError(t('auth.invalidPassword'));
        } else {
          setError(t('auth.loginFailed'));
        }
      } finally {
        setBusy(false);
      }
    })();
  };

  return (
    <Center mih="100vh" p="md">
      <Paper shadow="md" p="xl" radius="md" maw={400} w="100%">
        <form onSubmit={onSubmit}>
          <Stack gap="md">
            <div>
              <Title order={3}>{t('auth.title')}</Title>
              <Text size="sm" c="dimmed" mt={6}>
                {t('auth.subtitle')}
              </Text>
            </div>
            <PasswordInput
              label={t('auth.passwordLabel')}
              placeholder={t('auth.passwordPlaceholder')}
              value={password}
              onChange={(e) => setPassword(e.currentTarget.value)}
              autoComplete="current-password"
              disabled={busy}
              autoFocus
            />
            {error ? (
              <Text size="sm" c="red">
                {error}
              </Text>
            ) : null}
            <Button type="submit" loading={busy} fullWidth>
              {t('auth.signIn')}
            </Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
