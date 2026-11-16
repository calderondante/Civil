import type { Metadata } from "next";
import "./style.css";
export const metadata: Metadata = {
  title: "Academic Audio Studio",
  description: "Del material fuente al audio, con cada apartado a la vista.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es-AR">
      <body>{children}</body>
    </html>
  );
}
