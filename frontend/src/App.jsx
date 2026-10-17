// src/App.jsx
import { AppProvider, useApp } from './context/AppContext'
import Sidebar from './components/Sidebar'
import ChatArea from './components/ChatArea'
import InputBar from './components/InputBar'
import SettingsModal from './components/SettingsModal'
import LibraryModal from './components/LibraryModal'
import PronunciationModal from './components/PronunciationModal'
import TodayModal from './components/TodayModal'
import { VoiceProvider } from './hooks/useVoiceMode'

function AppLayout() {
  const { sidebarOpen } = useApp()

  return (
    <div className="flex h-screen overflow-hidden bg-white">
      {/* Sidebar retrátil */}
      <div className="relative flex shrink-0">
        <Sidebar />
      </div>

      {/* Área principal */}
      <main className="flex flex-col flex-1 overflow-hidden min-w-0">
        <ChatArea />
        <InputBar />
      </main>

      {/* Modal de configurações (overlay) */}
      <SettingsModal />
      <LibraryModal />
      <PronunciationModal />
      <TodayModal />
    </div>
  )
}

export default function App() {
  return (
    <AppProvider>
      <VoiceProvider>
        <AppLayout />
      </VoiceProvider>
    </AppProvider>
  )
}
