"use client"
 
import { Header } from "@bcgov/design-system-react-components";
import Image from "next/image";
import Link from "next/link"
import styles from "@/app/components/Navbar.module.scss"
 
type NavLink = {
  label: string
  href: string
}
 
const links: NavLink[] = [
  { label: "How To Use", href: "/how-to-use" }
]
 
export default function Navbar() {
  return (
    <Header
      title="Automated Statusing Tool"
      logoLinkElement={<a href="\" title="BC Government Website" />}
      logoImage={<Image className={styles.logo} src="/geobc-logo.png" alt="GeoBC Logo" width={200} height={60}/>}
    >
      <nav className={styles.links}>
        {links.map((link) => (
          <Link key={link.href} href={link.href}>
            {link.label}
          </Link>
        ))}
      </nav>
    </Header>
  )
}