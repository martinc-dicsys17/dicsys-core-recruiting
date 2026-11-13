import {
  Briefcase,
  Building2,
  Calculator,
  Circle,
  FileText,
  Folder,
  Headset,
  HeartHandshake,
  History,
  Key,
  Layers,
  LayoutDashboard,
  Lightbulb,
  List,
  Package,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Star,
  UserCheck,
  UserX,
  Users,
  Wallet,
} from '@lucide/vue'
import type { Component } from 'vue'

/**
 * El menu llega del backend con nombres de iconos Lucide (los mismos que usa el frontend actual).
 * Se importan solo los que se usan para no incluir la libreria completa en el bundle;
 * un nombre no listado cae en el icono generico.
 */
const ICONOS: Record<string, Component> = {
  briefcase: Briefcase,
  'building-2': Building2,
  calculator: Calculator,
  'file-text': FileText,
  headset: Headset,
  'heart-handshake': HeartHandshake,
  history: History,
  key: Key,
  layers: Layers,
  'layout-dashboard': LayoutDashboard,
  lightbulb: Lightbulb,
  list: List,
  package: Package,
  settings: Settings,
  'shield-check': ShieldCheck,
  'sliders-horizontal': SlidersHorizontal,
  star: Star,
  'user-check': UserCheck,
  'user-x': UserX,
  users: Users,
  wallet: Wallet,
}

export function iconoDeMenu(nombre: string | null, tipo: 'grupo' | 'item'): Component {
  return (nombre ? ICONOS[nombre] : undefined) ?? (tipo === 'grupo' ? Folder : Circle)
}
