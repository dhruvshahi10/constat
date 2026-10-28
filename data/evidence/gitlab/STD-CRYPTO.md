---
source_id: STD-CRYPTO
title: Cryptographic Standard
type: standard
version: "1.0"
effective_date: 2026-05-06
expiry_date: 2027-05-06
owner: security@gitlab.com
approval_status: approved
topics: encryption, tls, key management, cryptography
---

This is the GitLab Cryptography Standard. It outlined cryptographic choices, including algorithms as well as important settings that may be associated with the algorithms. It applies to GitLab code and well as infrastructure configuration.

In line with GitLab’s regulatory obligations, changes to 
 controlled documents must be approved or merged by a code owner. All contributions are welcome and encouraged.

The Cryptography Standard defines approved cryptographic algorithms, settings, and cryptographic modules for the purposes of encrypting data at rest or in transit within the various systems and subsystems used by the GitLab product.

The Cryptography Standard allows for a more consistent approach to cryptographic usage within GitLab, easier adaptation to industry standards and compliance frameworks (such as FedRAMP ), and an overall more secure product and working environment. In addition, most of the standards are based off of recommendations from NIST (National Institute of Standards and Technology) as many of the compliance frameworks are based off of NIST standards, and NIST consistently makes solid recommendations that are adopted by many organizations globally.

The Cryptography Standard applies to all GitLab team members, contractors, consultants, vendors and other service providers that handle, manage, store or transmit GitLab data.

This is required for coding best practices as well as client and server configurations involving cryptography for the GitLab product itself. Currently, there are numerous efforts internally by numerous Engineering teams ensuring these standards are met and maintained. The scope includes third party modules and software settings where cryptographic settings are required. Basically if it touches GitLab or GitLab customer data, the standard applies.

GitLab Team Members 
 Responsible for adhering to the requirements outlined in this standard

Security Management and Cryptographic Officer (Code Owners) 
 Responsible for approving significant changes and exceptions to this standard

- GitLab team members, contractors, consultants, vendors and other service providers are required to review and understand this cryptographic standard, and how to handle encryption needs for data at rest and in transit as defined below unless otherwise noted.

- GitLab customers are responsible for managing their own data, should consider these standards as highly recommended, and adopt them according to their own internal requirements. GitLab handles Customer Data internally according to our non-disclosure obligations written in our Mutual Non Disclosure Agreement, and we use the controls identified in this standard.

While we consider these standards to be a security baseline to improve the overall security of the GitLab product, for compliance and certification efforts we will be using the following general guidelines.

- No non-public cryptographic modules. All cryptographic modules should be open source and well maintained. This is to ensure compliance with the Bureau of Industry (BIS) and Security’s Export Administration Regulations regarding encryption .

- All product development shall include support for GitLab’s FIPS releases, following the patterns specified in the FIPS development documentation on the roadmap. New features that are not leveraging underlying FIPS-validated cryptographic modules cannot be made available to customers who use our FIPS releases or Dedicated for Government offering. They should be disabled by default behind a feature flag or, if not possible, an option to disable the feature entirely.

- All cryptographic choices (algorithms, etc) will adhere to FIPS 140-3 minimum standards (which superseded FIPS 140-2 on 03/22/2019), and keep in mind NIST SP 800-53 as well.

- When possible, choose quantum-resistant algorithms as an effort to help “future proof” cryptographic choices as quantum computing usage becomes more powerful and more mainstream. For more information read the section on quantum cryptography here .

Meeting these standards will help meet objectives such as FedRAMP compliance , but as standards such as FIPS and SP 800-53 are considered de facto global standards, it will help with compliance needs in multiple countries and industries.

For regulatory requirements (such as FIPS), all cryptographic modules must be publicly available (open source) to ensure compliance with the Bureau of Industry and Security’s Export Administration Regulations regarding encryption . As this compliance meets international standards per the Wassenaar Arrangement this should meet any requirements that might be encountered globally, should the situation arise.

The choice of cryptographic modules is important. It is possible that GitLab features that have cryptographic elements could find themselves having to meet stringent module requirements (FedRAMP standards, running in FIPS mode, etc) so adherence to specific modules is highly recommended. This includes the following:

For the gitlab-fips package , all FIPS-validated cryptographic modules are documented on the “FIPS Compliance” Docs page, currently located here . This documentation must be kept up to date to maintain GitLab’s FedRAMP and FIPS 140-2 compliance posture.

Note to developers and contributors, regardless of FIPS/FedRAMP compliance or not, coding should use the cryptographic modules mentioned above. Development with a non-FIPS version of the same module (e.g. openssl-x.y.x vs openssl-x.y.z-fips ) is fine. The important point is to not introduce new code that is dependent on cryptographic modules that do not have a FIPS version or have written their own cryptographic implementations of algorithms. A list of FIPS-certified cryptographic modules can be found here .

Periodic changes to this standard can and will occur as cryptographic module upgrades and availability happen, updates or changes to cryptography in general occur, and new supported Linux server images that GitLab supports become available.

- TLS - TLS TLS 1.3 must be enabled and preferred in all new deployments. TLS 1.2 MAY remain enabled for legacy interoperability but MUST NOT be the only supported TLS version. TLS 1.0 and 1.1 are not allowed, despite being FIPS 140-2 compliant. FIPS 140-3 and SP 800-53 standards disallow TLS 1.0 and 1.1 explicitly, as does FedRAMP which follows those same guidelines.
 
- Here are the algorithms that should be used:
 
- ECDHE-ECDSA-AES256-GCM-SHA384

- In regards to coding practices, refer to the secure coding guidelines , in particular for language-specific guidelines as well as limitations.

- ML-KEM is a NIST-approved quantum safe algorithm. Specifically ML-KEM-1024 is recommended. Just note that ML-KEM can only be used in a FIPS environment if it is using a FIPS-certified cryptographic module. For more information see this section .

- Block Ciphers - AES . Currently AES-128 is considered the minimal, but to ensure “future proofing” AES-256 is preferred (note there are potential performance impacts depending upon application usage, etc). GCM is the required mode (e.g. aes-256-gcm ).
 
- It should be noted that AES-256 is considered quantum resistant while AES-128 is not, which is also another consideration for future proofing.

- Per SP 800-131A Rev.3 AES-ECB mode is not to be used at all. Use AEAD modes such as AES‑GCM (or AES‑CCM / AES‑KW / AES‑KWP where appropriate).

- NOTE for Laptops: For full-disk encryption XTS-AES-128 (with 256 bit key) or XTS-AES-256 (with 512 bit key) is acceptable. For both GitLab-approved laptop scenarios for team members (Apple running MacOS or a Linux-based laptop running Ubuntu) one of these two algorithms is automatically pre-chosen and is acceptable when setting up full disk encryption on a laptop.

- Digital Signatures - RSA , ECDSA , and EdDSA . For RSA, the minimum key size is 2048. For ECDSA the minimum key size is 256. Ed25519 and Ed448 are now both approved algorithms if the underlying crypto module has included it in its certification, however at this time our OpenSSL implementation does not certify it . For new implementations using ECDSA, ECC keys MUST be ≥256 bits (e.g., P‑256, P‑384). Curves with order length <256 bits (e.g., P‑224) are considered legacy only and MUST NOT be used for new digital signatures.
 
- ML-DSA is a NIST-approved quantum safe algorithm. Specifically ML-DSA-87 with a random seed of 256 bits is recommended. Just note that ML-DSA can only be used in a FIPS environment if it is using a FIPS-certified cryptographic module. For more information see this section .

- SLH-DSA is a NIST-approved quantum safe algorithm. SLH-DSA’s strength lies in functioning as a replacement of digital signatures based only on known-strong hash function design. It replaces stateful hash-based signatures such as LMS and XMSS with a probabilistic construction and does not rely on math such as discrete log or lattices. Just note that SLH-DSA can only be used in a FIPS environment if it is using a FIPS-certified cryptographic module. For more information see this section . Generally ML-DSA is preferred to SLH-DSA except for applications with a long time-horizon or tight hardware constraints (such as embedded contexts).

- Hash Functions - The SHA-2 family of hash algorithm, with SHA-256 as the minimum. Ideally SHA-384 or higher would be better, although there might be less support particularly in third party software.
 
- It should be noted that while SHA-1 is FIPS 140-2 compliant, per NIST SP 800-53 Rev 5 Baselines it is not allowed. This is per SP-800-57 section 5.6.1.2, SP-800-131 section 9 table 8, and SP-800-107 section 4.

- It should be noted that SHA-2-256+ and SHA-3-256+ are considered quantum resistant .

- MAC - MAC ( Message Authentication Code ) is usually implemented to authenticate messages as unaltered after transmission. A MAC is to only be used in conjunction with an approved algorithm, and with the following parameters:
 
- HMAC , KMAC. Only with a key length equal to or greater than 128 bits.

- CMAC , GMAC . Only in conjunction with AES; HMAC is generally preferred to CMAC. GMAC should not be used for general purposes.

- Random Number Generation - True random number generation is not required, but a high level of randomization is still important. The preference is to use pseudo-random number generation using /dev/random . While /dev/urandom is not as secure, historically it performed quicker on much older systems. When the underlying operating system is running in FIPS mode, calls to /dev/urandom are directed to /dev/random , and starting with Linux kernel version 5.18 both /dev/random and /dev/urandom will function the same anyway. Therefore the standard is /dev/random .

- Password Hashes - Currently the GitLab product uses the popular Bcrypt algorithm for user account password hashing by default. Bcrypt is not an approved FIPS 140-2 algorithm, so development engineers have added support for PBKDF2+SHA512 starting with GitLab version 15.2 via feature flags, and starting with 15.6 it is available when FIPS-mode is enabled. More details are available here . Key stretching is used for both algorithms, with Bcrypt’s factor set to 13 (as of GitLab version 18.0) and PBKDF2+SHA512’s factor set to 20,000. Passwords should be salted with a unique salt using one of the approved cryptographic one-way hashes above before Bcrypt or PBKDF2+SHA512 are used, as this will further strengthen the password hash against brute force and dictionary style attacks.

- Note on Older/Alternate Algorithms - Notes on a few other popular algorithms:
 
- DSA is no longer an approved algorithm per FIPS 186-5 and is largely regarded as a weak cipher.

- SHA-1 - For hashing algorithms, SHA-1 is allowed for non-cryptographic functions (such as a checksum). It is not allowed for digital signature generation. For digital signature validation, SHA-1 is allowed. For non-digital-signature applications, SHA-1 is allowed if collision resistance is not required, such as an initialization vector of a block cipher that doesn’t require randomization. For more details on SHA-1 usage, refer to NIST SP 800-131A Rev 3 , especially section 9 on key derivation methods. As SHA-1 will eventually no longer be allowed in various standards in the future, use SHA-256 whenever possible. SHA‑1 and 224‑bit hash variants (including SHA‑224, SHA‑512/224, SHA3‑224) are only permitted for strictly legacy verification scenarios and MUST NOT be used to apply new cryptographic protection, in line with NIST SP 800‑131A Rev.3’s retirement schedule.

- MD5 - Previously, MD5 was allowed for non-cryptographic functions. However as a result of initial audit findings from May 2, 2022 MD5 is no longer allowed, whether the function is cryptographic or not. For FIPS compliance MD5 cannot be used at all.

Quantum computing allows for advanced mathematical calculations, and as quantum-based computers evolve and become more powerful, there is a danger of certain algorithms being able to be broken or “cracked” - namely a number of algorithms that use a form of factoring large numbers as a part of the cracking effort. So there is concern that when this point is reached, many cryptographic algorithms will no long be considered secure. Using Shor’s algorithm (and it’s variants) running on a cryptographically relevant quantum computer (CRQC) can break the asymmetric algorithms (RSA, ECDSA, and so on), hence the danger. Additionally, using Grover’s algorithm on a CRQC can “weaken” symmetric algorithms, where AES-128 is weakened to the equivalent of AES-64 and so on. This is in part why AES-128 has fallen out of favor and AES-256 is considered the minimum. Ideally one could run AES-384 or AES-512 for even more strength, but while it is the same AES algorithm, running it with 384 or 512 bits was not a part of the approved AES recommendations from NIST.

The current scenario is often referred to as “Post Quantum Cryptography”, or PQC for short. This differs from Quantum Cryptography: the former runs on present computing hardware while the latter requires specialized quantum-aware hardware (sometimes also referred to as quantum key distribution (QKD)). Another concept to keep in mind is the threat of what is referred to as “ harvest-now, decrypt later ”. If encrypted information is intended on remaining secret for around 5 to 10 years from 2026, it is highly recommended that the use of cryptographically-approved quantum safe algorithms be implemented as soon as possible.

In preparation for adopting the new NIST PQC Algorithms , GitLab will consider the following:

- Where possible, choose existing cryptographic algorithms that are already known to be resistant to cracking via quantum computing, commonly known as “quantum resistant”.

- As new quantum resistant algorithms are included in operating system libraries and are certified in FIPS environments, the standards listed above will be updated.

- GitLab will begin testing these algorithms (ML-KEM, ML-DSA, and SLH-DSA) to ensure that we will be able to migrate to their implementation as more adoption occurs. The testing will begin when quantum-supporting versions of the OpenSSL Cryptographic Module, the Linux Kernel Crypto API Cryptographic Module, and the Libgcrypt Cryptographic Module have been added to base operating systems (for example Ubuntu Server LTS and RHEL) which are a part of our underlying infrastructure.

- As of August 13, 2024 NIST published the final versions of FIPS 203 , FIPS 204 , and FIPS 205 . Currently the quantum safe algorithms referenced in these standards are approved for use. Ensure that any use of these algorithms in a FIPS environment are using FIPS certified cryptographic modules. Quantum safe cryptographic modules do exist (such as liboqs and OpenSSL 3.5.0 ), but as of April 2026 none of the existing quantum safe cryptographic modules are FIPS certified.

- The parameters GitLab will support for quantum algorithms include those listed in Commercial National Security Algorithm Suite (CNSA) version 2.0 . A summary can be found here , and these are noted in the references to parameters in the algorithm standards mentioned above .

- Hybrid solutions exist for quantum algorithms in some cases, but GitLab will strongly prefer pure quantum algorithmic deployment over hybrid solutions to ensure full FIPS and FedRAMP compliance.

- Not all variations of configurations will be tested in certain specific scenarios. For example in a standalone instance of GitLab there are currently no plans for extensive testing of every possible SSL configuration, as configuration options (like all optional features) will be up to GitLab customers’ standards and needs.

- As the modules that support PQC become a part of Linux images that GitLab has historically used and will continue to use, the PQC-aware cryptographic modules will be tested as part of the standard process for validating new stable Linux images. PQC algorithms will eventually become a part of the available configuration options. An official roadmap will be developed once these PQC-enabled Linux images become available.

- Specific testing for FedRAMP images using PQC settings will occur when FIPS-certified Linux images with PQC modules become available.

- While there is currently no specific timeline for PQC compliance within GitLab’s offerings, historical testing patterns and the normal release cadence of new Linux images suggest that full PQC compliance within GitLab may occur before 2030.

Exceptions to this policy will be tracked as per the Information Security Policy Exception Management Process .
