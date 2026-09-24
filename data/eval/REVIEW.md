# Evaluation set — review sheet

Drafted from the real text of 65 acts. For each question: is it natural, is the gold section right,
is the reference answer accurate and short? Edit `data/eval/eval.jsonl` / `tune.jsonl` directly, or
list the ids to change and I will do it.

96 reported questions (`eval.jsonl`) + 24 tuning questions (`tune.jsonl`, used only to pick weights/thresholds).

## pc01 · single · en · eval
**Q:** What is the punishment for murder in Bangladesh?  
**A:** Death or imprisonment for life, and the offender is also liable to fine (Penal Code s.302).  
> **[11:3131] §302 Punishment for murder** — 302. Whoever commits murder shall be punished with death, or [imprisonment] for life, and shall also be liable to fine.…

## pc02 · multi · bn · eval
**Q:** অবহেলা করে গাড়ি চালিয়ে কারো মৃত্যু ঘটালে কী শাস্তি হতে পারে?  
**A:** বেপরোয়া বা অবহেলাজনিত গাড়ি চালনায় মৃত্যু ঘটালে তিন বছর পর্যন্ত কারাদণ্ড বা জরিমানা বা উভয় দণ্ড (ধারা ৩০৪খ); সাধারণ অবহেলাজনিত মৃত্যুতে পাঁচ বছর পর্যন্ত (ধারা ৩০৪ক)।  
*note:* paraphrase of rash driving  
> **[11:3135] §304B Causing death by rash driving or riding on a public way** — [304B. Whoever causes the death of any person by rash or negligent driving of any vehicle or riding on any public way not amounting to culpable homicide shall be punished with imprisonment of either description for a term which may extend to [three years], or with fine, or with both.]…
> **[11:3134] §304A Causing death by negligence** — [304A. Whoever causes the death of any person by doing any rash or negligent act not amounting to culpable homicide shall be punished with imprisonment of either description for a term which may extend to [five] years, or with fine, or with both.]…

## pc03 · paraphrase · en · eval
**Q:** When does taking someone's thing count as theft?  
**A:** Theft is dishonestly moving movable property out of another person's possession without their consent, intending to take it (s.378).  
> **[11:3234] §378 Theft** — 378. Whoever, intending to take dishonestly any moveable property out of the possession of any person without that person's consent, moves that property in order to such taking, is said to commit theft.  Explanation 1.-A thing so long as it is attached to the earth, not being moveable property, is not the subject of theft; but it becomes capable of…

## pc04 · single · bn · eval
**Q:** চুরির শাস্তি কী?  
**A:** চুরির জন্য তিন বছর পর্যন্ত যেকোনো বর্ণনার কারাদণ্ড, বা জরিমানা, বা উভয় দণ্ড (ধারা ৩৭৯)।  
> **[11:3235] §379 Punishment for theft** — 379. Whoever commits theft shall be punished with imprisonment of either description for a term which may extend to three years, or with fine, or with both.…

## pc05 · exact_ref · en · eval
**Q:** What does section 420 of the Penal Code say?  
**A:** Cheating and thereby dishonestly inducing delivery of property is punishable with up to seven years' imprisonment and fine.  
> **[11:3366] §420 Cheating and dishonestly inducing deliver of property** — 420. Whoever cheats and thereby dishonestly induces the person deceived to deliver any property to any person, or to make, alter or destroy the whole or any part of a valuable security, or anything which is signed or sealed, and which is capable to being converted into a valuable security, shall be punished with imprisonment of either description f…

## pc06 · paraphrase · bn · eval
**Q:** কাউকে মিথ্যা অপবাদ দিয়ে সম্মানহানি করলে সর্বোচ্চ কত বছরের জেল হতে পারে?  
**A:** মানহানির জন্য দুই বছর পর্যন্ত বিনাশ্রম কারাদণ্ড, বা জরিমানা, বা উভয় দণ্ড (ধারা ৫০০)।  
> **[11:3551] §500 Punishment for defamation** — 500. Whoever defames another shall be punished with simple imprisonment for a term which may extend to two years, or with fine, or with both.…

## pc07 · paraphrase · en · eval
**Q:** Can a seven-year-old child be punished for a crime?  
**A:** No. Nothing is an offence which is done by a child under nine years of age (s.82).  
> **[11:2755] §82 Act of a child under nine years of age** — 82. Nothing is an offence which is done by a child under [nine] years of age.…

## pc08 · single · en · eval
**Q:** A 10-year-old who did not understand what he was doing caused harm. Is it an offence?  
**A:** Not if the child, being above nine and under twelve, lacked the maturity to judge the nature and consequences of the act (s.83).  
> **[11:2756] §83 Act of a child above nine and under twelve of immature understanding** — 83. Nothing is an offence which is done by a child above [nine] years of age and under twelve, who has not attained sufficient maturity of understanding to judge of the nature and consequences of his conduct on that occasion.…

## pc09 · single · bn · tune
**Q:** আত্মরক্ষা করতে গিয়ে কাউকে আঘাত করলে কি অপরাধ হয়?  
**A:** আত্মরক্ষার অধিকার প্রয়োগে করা কোনো কাজ অপরাধ নয় (ধারা ৯৬)।  
> **[11:2771] §96 Things done in private defence** — 96. Nothing is an offence which is done in the exercise of the right of private defence.…

## pc10 · single · en · tune
**Q:** When can self-defence extend to killing the attacker?  
**A:** When the assault reasonably causes apprehension of death or grievous hurt, or in the other cases listed in s.100 (e.g. rape, kidnapping, acid attack).  
> **[11:2776] §100 When the right of private defence of the body extends to causing death** — 100. The right of private defence of the body extends, under the restrictions mentioned in the last preceding section, to the voluntary causing of death or of any other harm to the assailant, if the offence which occasions the exercise of the right be of any of the descriptions hereinafter enumerated, namely:-  Firstly.-Such an assault as may reaso…

## pc11 · exact_ref · bn · eval
**Q:** দণ্ডবিধির ধারা ৩৪ কী বলে?  
**A:** একাধিক ব্যক্তি সকলের অভিন্ন অভিপ্রায় সাধনে কোনো অপরাধমূলক কাজ করলে প্রত্যেকে এমনভাবে দায়ী যেন কাজটি সে একাই করেছে।  
> **[11:2122] §34 Acts done by several persons in furtherance of common intention** — 34. When a criminal act is done by several persons, in furtherance of the common intention of all, each of such persons is liable for that act in the same manner as if it were done by him alone.…

## pc12 · single · en · eval
**Q:** What is criminal breach of trust?  
**A:** Dishonestly misappropriating or converting property one has been entrusted with, or using it in violation of law or contract (s.405).  
> **[11:3270] §405 Criminal breach of trust** — 405. Whoever, being in any manner entrusted with property, or with any dominion over property, dishonestly misappropriates or converts to his own use that property, or dishonestly uses or disposes of that property in violation of any direction of law prescribing the mode in which such trust is to be discharged, or of any legal contract, express or …

## pc13 · multi · bn · eval
**Q:** জাল দলিল বানানোর শাস্তি কী?  
**A:** জালিয়াতির জন্য দুই বছর পর্যন্ত কারাদণ্ড বা জরিমানা বা উভয় (ধারা ৪৬৫); ক্ষতি বা প্রতারণার উদ্দেশ্যে মিথ্যা দলিল তৈরি জালিয়াতি (ধারা ৪৬৩)।  
> **[11:3449] §465 Punishment for forgery** — 465. Whoever commits forgery shall be punished with imprisonment of either description for a term which may extend to two years, or with fine, or with both.…
> **[11:3447] §463 Forgery** — 463. Whoever makes any false document or part of a document, with intent to cause damage or injury, to the public or to any person, or to support any claim or title, or to cause any person to part with property, or to enter into any express or implied contract, or with intend to commit fraud or that fraud may be committed, commits forgery.…

## pc14 · single · en · eval
**Q:** What is the punishment for kidnapping?  
**A:** Imprisonment of either description up to seven years, and fine (s.363).  
> **[11:3216] §363 Punishment for kidnapping** — 363. Whoever kidnaps any person from Bangladesh or from lawful guardianship, shall be punished with imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine.…

## pc15 · single · en · eval
**Q:** Is attempting suicide a crime in Bangladesh?  
**A:** Yes. Attempting suicide is punishable with simple imprisonment up to one year, or fine, or both (s.309).  
> **[11:3140] §309 Attempt to commit suicide** — 309. Whoever attempts to commit suicide and does any act towards the commission of such offence, shall be punished with simple imprisonment for a term which may extend to one year, or with fine, or with both.…

## pc16 · exact_ref · mixed · eval
**Q:** Penal Code এর ধারা ৩০২ এ কী আছে?  
**A:** খুনের শাস্তি মৃত্যুদণ্ড বা যাবজ্জীবন কারাদণ্ড এবং অর্থদণ্ড।  
*note:* code-switched  
> **[11:3131] §302 Punishment for murder** — 302. Whoever commits murder shall be punished with death, or [imprisonment] for life, and shall also be liable to fine.…

## pc17 · paraphrase · en · tune
**Q:** Is it a crime for a government officer to accept money for doing his official work?  
**A:** Yes. A public servant who accepts gratification other than legal remuneration as a motive or reward for an official act commits an offence (s.161).  
> **[11:2896] §161 Public servant taking gratification other than legal remuneration in respect of an official ac** — 161. Whoever, being or expecting to be a public servant, accepts or obtains, or agrees to accept, or attempts to obtain from any person, for himself or for any other person any gratification whatever, other than legal remuneration, as a motive or reward for doing or forbearing to do any official act or for showing or for bearing to show, in the exe…

## pc18 · single · bn · eval
**Q:** কোনো নারীর শ্লীলতাহানির উদ্দেশ্যে আক্রমণ করলে দণ্ডবিধিতে কী শাস্তি?  
**A:** দুই বছর পর্যন্ত কারাদণ্ড, বা জরিমানা, বা উভয় দণ্ড (ধারা ৩৫৪)।  
> **[11:3207] §354 Assault or criminal force to woman with intent to outage her modesty** — 354. Whoever assaults or uses criminal force to any woman, intending to outrage or knowing it to be likely that he will thereby outrage her modesty, shall be punished with imprisonment of either description for a term which may extend to two years, or with fine, or with both.…

## cr01 · single · en · eval
**Q:** When can the police arrest someone without a warrant?  
**A:** For example when a person commits a cognizable offence in a police officer's presence, or on a reasonable complaint, credible information or reasonable suspicion of a cognizable offence, subject to the conditions in s.54.  
> **[75:14518] §54 When police may arrest without warrant** — [54. (1) Any police-officer may, without an order from a Magistrate and without warrant, arrest-  firstly, any person who commits, in the presence of a police-officer, a cognizable offence;  secondly, any person against whom a reasonable complaint has been made, or credible information has been received, or a reasonable suspicion exists that he has…

## cr02 · multi · bn · eval
**Q:** গ্রেফতারের পর পুলিশ কাউকে ম্যাজিস্ট্রেটের আদেশ ছাড়া সর্বোচ্চ কতক্ষণ আটকে রাখতে পারে?  
**A:** যাত্রার সময় বাদে চব্বিশ ঘণ্টার বেশি নয় (ফৌজদারী কার্যবিধি ধারা ৬১; সংবিধানের অনুচ্ছেদ ৩৩)।  
*note:* needs CrPC + Constitution  
> **[75:14525] §61 Person arrested not to be detained more than twenty-four hours** — 61. No police-officer shall detain in custody a person arrested without warrant for a longer period than under all the circumstances of the case is reasonable, and such period shall not, in the absence of a special order of a Magistrate under section 167, exceed twenty-four hours exclusive of the time necessary for the journey from the place of arr…
> **[367:24581] §33 Safeguards as to arrest and detention** — [33. (1) No person who is arrested shall be detained in custody without being informed, as soon as may be, of the grounds for such arrest, nor shall he be denied the right to consult and be defended by a legal practitioner of his choice.  (2) Every person who is arrested and detained in custody shall be produced before the nearest magistrate within…

## cr03 · exact_ref · en · eval
**Q:** What does section 144 of the CrPC allow a magistrate to do?  
**A:** In urgent cases, a District or specially empowered Executive Magistrate may by written order direct a person to abstain from an act, to prevent obstruction, danger or disturbance of the public tranquillity.  
> **[75:20789] §144 Power to issue order** — 144.(1) In cases where, in the opinion of a District Magistrate, [or any other Executive Magistrate] specially empowered by the Government or the District Magistrate to act under this section, there is sufficient ground for proceeding under this section and immediate prevention or speedy remedy is desirable,  such Magistrate may, by a written order…

## cr04 · single · en · eval
**Q:** How is an FIR recorded when someone reports a cognizable offence to the police?  
**A:** Oral information is written down by the officer in charge, read over to the informant and signed, and its substance entered in the prescribed book (s.154).  
> **[75:20845] §154 Information in cognizable cases** — 154. Every information relating to the commission of a cognizable offence if given orally to an officer in charge of a police-station, shall be reduced to writing by him or under his direction, and be read over to the informant; and every such information, whether given in writing or reduced to writing as aforesaid, shall be signed by the person gi…

## cr05 · single · bn · tune
**Q:** ম্যাজিস্ট্রেট কীভাবে আসামির স্বীকারোক্তি রেকর্ড করেন?  
**A:** মেট্রোপলিটন বা প্রথম শ্রেণির ম্যাজিস্ট্রেট (বা ক্ষমতাপ্রাপ্ত দ্বিতীয় শ্রেণির) তদন্ত চলাকালে বা বিচার শুরুর আগে স্বীকারোক্তি রেকর্ড করতে পারেন; তিনি পুলিশ কর্মকর্তা হতে পারবেন না (ধারা ১৬৪)।  
> **[75:20858] §164 Power to record statements and confessions** — 164.(1) [Any Metropolitan Magistrate, any Magistrate of the first class] and any Magistrate of the second class specially empowered in this behalf by the Government may, if he is not a police-officer record any statement or confession made to him in the course of an investigation under this Chapter or at any time afterwards before the commencement …

## cr06 · single · en · eval
**Q:** What happens if the police cannot finish an investigation within 24 hours of arrest?  
**A:** The accused must be forwarded to a Magistrate with the case diary, who may authorise further detention in custody within the limits of s.167.  
> **[75:20861] §167 Procedure when investigation cannot be completed in twenty-four hours** — 167.(1) Whenever any person is arrested and detained in custody, and it appears that the investigation cannot be completed within the period of twenty-four hours fixed by section 61, and there are grounds for believing that the accusation or information is well-founded, the officer in charge of the police-station or the police-officer making the in…

## cr07 · single · bn · tune
**Q:** জামিন অযোগ্য অপরাধে অভিযুক্ত হলে কি জামিন পাওয়া যায়?  
**A:** হ্যাঁ, জামিন দেওয়া যেতে পারে, তবে মৃত্যুদণ্ড বা যাবজ্জীবনযোগ্য অপরাধে দোষী হওয়ার যুক্তিসঙ্গত কারণ থাকলে নয়; ষোল বছরের কম বয়সী, নারী বা অসুস্থ ব্যক্তিকে আদালত জামিন দিতে পারে (ধারা ৪৯৭)।  
> **[75:22016] §497 When bail may be taken in case of non-bailable offence** — 497.(1) When any person accused of any non-bailable offence is arrested or detained without warrant by an officer in charge of a police-station, or appears or is brought before a Court, he may be released on bail, but he shall not be so released if there appear reasonable grounds for believing that he has been guilty of an offence punishable with d…

## cr08 · exact_ref · mixed · eval
**Q:** CrPC section 54 এ police কী ক্ষমতা পায়?  
**A:** ম্যাজিস্ট্রেটের আদেশ ও ওয়ারেন্ট ছাড়াই নির্দিষ্ট শর্তে গ্রেফতারের ক্ষমতা।  
*note:* code-switched  
> **[75:14518] §54 When police may arrest without warrant** — [54. (1) Any police-officer may, without an order from a Magistrate and without warrant, arrest-  firstly, any person who commits, in the presence of a police-officer, a cognizable offence;  secondly, any person against whom a reasonable complaint has been made, or credible information has been received, or a reasonable suspicion exists that he has…

## cr09 · single · en · tune
**Q:** Can the High Court reduce the bail amount set by a magistrate?  
**A:** Yes. The High Court Division or Court of Session may direct admission to bail or that bail required by a police officer or Magistrate be reduced (s.498).  
> **[75:22018] §498 Power to direct admission to bail or reduction of bail** — 498. [(1)] The amount of every bond executed under this Chapter shall be fixed with due regard to the circumstances of the case, and shall not be excessive; and the High Court Division or Court of Session may, in any case, whether there be an appeal on conviction or not, direct that any person be admitted to bail, or that the bail required by a pol…

## co01 · exact_ref · en · eval
**Q:** What does Article 27 of the Constitution say?  
**A:** All citizens are equal before law and are entitled to equal protection of law.  
> **[367:24575] §27 Equality before law** — 27. All citizens are equal before law and are entitled to equal protection of law.…

## co02 · single · bn · eval
**Q:** সংবিধান অনুযায়ী কি মতপ্রকাশের স্বাধীনতার নিশ্চয়তা আছে?  
**A:** হ্যাঁ; চিন্তা ও বিবেকের স্বাধীনতা এবং আইনের যুক্তিসঙ্গত বাধানিষেধ সাপেক্ষে বাক ও ভাব প্রকাশের এবং সংবাদক্ষেত্রের স্বাধীনতার নিশ্চয়তা দেওয়া হয়েছে (অনুচ্ছেদ ৩৯)।  
> **[367:24587] §39 Freedom of thought and conscience, and of speech** — 39. (1) Freedom of thought and conscience is guaranteed.  (2) Subject to any reasonable restrictions imposed by law in the interests of the security of the State, friendly relations with foreign states, public order, decency or morality, or in relation to contempt of court, defamation or incitement to an offence–  (a) the right of every citizen to …

## co03 · paraphrase · en · eval
**Q:** Can the state take away someone's life or liberty?  
**A:** Only in accordance with law: no person shall be deprived of life or personal liberty save in accordance with law (Art. 32).  
> **[367:24580] §32 Protection of right to life and personal liberty** — 32. No person shall be deprived of life or personal liberty save in accordance with law.…

## co04 · single · en · eval
**Q:** Does an arrested person have the right to a lawyer?  
**A:** Yes. An arrested person must be told the grounds of arrest and may not be denied the right to consult and be defended by a legal practitioner of his choice (Art. 33(1)).  
> **[367:24581] §33 Safeguards as to arrest and detention** — [33. (1) No person who is arrested shall be detained in custody without being informed, as soon as may be, of the grounds for such arrest, nor shall he be denied the right to consult and be defended by a legal practitioner of his choice.  (2) Every person who is arrested and detained in custody shall be produced before the nearest magistrate within…

## co05 · single · en · tune
**Q:** What is the minimum age to become a member of Parliament?  
**A:** A citizen of Bangladesh who has attained the age of twenty-five years (Art. 66(1)).  
> **[367:24620] §66 Qualifications and disqualifications for election to Parliament** — 66. (1) A person shall subject to the provisions of clause (2), be qualified to be elected as, and to be, a member of Parliament if he is a citizen of Bangladesh and has attained the age of twenty-five years.  (2) A person shall be disqualified for election as, or for being, a member of Parliament who –  (a) is declared by a competent court to be o…

## co06 · single · bn · eval
**Q:** রাষ্ট্রপতি কীভাবে নির্বাচিত হন?  
**A:** সংসদ-সদস্যদের দ্বারা আইন অনুযায়ী নির্বাচিত হন (অনুচ্ছেদ ৪৮(১))।  
> **[367:24597] §48 The President** — 48. (1) There shall be a President of Bangladesh who shall be elected by members of Parliament in accordance with law.  (2) The President shall, as Head of State, take precedence over all other persons in the State, and shall exercise the powers and perform the duties conferred and imposed on him by this Constitution and by any other law.  (3) In t…

## la01 · single · bn · eval
**Q:** শ্রমিকের দৈনিক কর্মঘণ্টা কত?  
**A:** সাধারণত দৈনিক আট ঘণ্টার বেশি নয়; ধারা ১০৮ সাপেক্ষে দৈনিক দশ ঘণ্টা পর্যন্ত কাজ করানো যায় (ধারা ১০০)।  
> **[952:29427] §১০০ দৈনিক কর্মঘণ্টা** — ১০০। কোন প্রাপ্তবয়স্ক শ্রমিক কোন প্রতিষ্ঠানে সাধারণতঃ দৈনিক আট ঘণ্টার অধিক সময় কাজ করিবেন না বা তাহাকে দিয়ে কাজ করানো যাইবে নাঃ  তবে শর্ত থাকে যে, ধারা ১০৮ এর বিধান সাপেক্ষে কোন প্রতিষ্ঠানে উক্তরূপ কোন শ্রমিক দৈনিক দশ ঘণ্টা পর্যন্ত ও কাজ করিতে পারিবেন।…

## la02 · single · en · eval
**Q:** How much maternity leave does a female worker get under the Labour Act?  
**A:** Maternity benefit for 60 days before and 60 days after the expected date of delivery, if she has worked at least six months for the employer (s.46).  
> **[952:26452] §৪৬ প্রসূতি কল্যাণ সুবিধা প্রাপ্তির অধিকার এবং প্রদানের দায়িত্ব** — ৪৬। (১) প্রত্যেক নারী শ্রমিক তাহার মালিকের নিকট হইতে তাহার সন্তান প্রসবের সম্ভাব্য তারিখের অব্যবহিত পূর্ববর্তী [৬০ (ষাট) দিন] এবং সন্তান প্রসবের অব্যবহিত পরবর্তী [৬০ (ষাট) দিনের] জন্য প্রসূতি কল্যাণ সুবিধা পাইবার অধিকারী হইবেন, এবং তাহার মালিক তাহাকে এই সুবিধা প্রদান করিতে বাধ্য থাকিবেনঃ  তবে শর্ত থাকে যে, কোন নারী উক্তরূপ সুবিধা পাইবেন না যদি না ত…

## la03 · single · bn · eval
**Q:** স্থায়ী শ্রমিককে ছাঁটাই ছাড়া চাকরি থেকে বাদ দিতে মালিককে কত দিনের নোটিশ দিতে হয়?  
**A:** মাসিক মজুরির শ্রমিকের ক্ষেত্রে একশত বিশ দিনের এবং অন্য শ্রমিকের ক্ষেত্রে ষাট দিনের লিখিত নোটিশ (ধারা ২৬(১))।  
> **[952:29913] §২৬ বরখাস্ত, ইত্যাদি ব্যতীত অন্যভাবে মালিক কতৃর্ক শ্রমিকের চাকুরীর অবসান** — ২৬। (১) এই অধ্যায়ের অন্যত্র বিধৃত কোন পন্থা ছাড়াও মালিক-  (ক) মাসিক মজুরীর ভিত্তিতে নিয়োজিত শ্রমিকের ক্ষেত্রে, একশত বিশ দিনের,  (খ) অন্য শ্রমিকের ক্ষেত্রে, ষাট দিনের,  লিখিত নোটিশ প্রদান করিয়া কোন স্থায়ী শ্রমিকের চাকুরীর অবসান করিতে পারিবেন।  (২) এই অধ্যায়ের অন্যত্র বিধৃত কোন পন্থা ছাড়াও মালিক-  (ক) মাসিক মজুরীর ভিত্তিতে নিয়োজিত শ্রমিকের ক্…

## la04 · single · bn · eval
**Q:** ওভারটাইম করলে শ্রমিক কী হারে ভাতা পাবেন?  
**A:** নির্দিষ্ট সময়ের অতিরিক্ত কাজের জন্য সাধারণ হারের দ্বিগুণ হারে ভাতা (ধারা ১০৮)।  
> **[952:29435] §১০৮ অধিকাল কর্মের জন্য অতিরিক্ত ভাতা** — ১০৮। (১) যে ক্ষেত্রে কোন শ্রমিক কোন প্রতিষ্ঠানে কোন দিন বা সপ্তাহে এই আইনের অধীন নির্দিষ্ট সময়ের অতিরিক্ত সময় কাজ করেন, সে ক্ষেত্রে তিনি অধিকাল কাজের জন্য তাহার মূল মজুরী ও মহার্ঘভাতা এবং এডহক বা অন্তবর্তী মজুরী, যদি থাকে, এর সাধারণ হারের দ্বিগুণ হারে ভাতা পাইবেন।  [ (২) ঠিকা-হার (পিস রেট) ভিত্তিতে মজুরিপ্রাপ্ত শ্রমিকগণের ক্ষেত্রে উপ-ধারা (১) এর …

## la05 · paraphrase · en · eval
**Q:** Can a factory employ a child?  
**A:** No. No child may be employed or permitted to work in any occupation or establishment; an adolescent only with a doctor's fitness certificate (s.34).  
> **[952:26435] §৩৪ শিশু ও কিশোর নিয়োগে বাধা-নিষেধ** — ৩৪। (১) কোন পেশায় বা প্রতিষ্ঠানে কোন শিশুকে নিয়োগ করা যাইবে না বা কাজ করিতে দেওয়া যাইবে না।  (২) কোন পেশায় বা প্রতিষ্ঠানে কোন কিশোরকে নিয়োগ করা যাইবে না বা কাজ করিতে দেওয়া যাইবে না, যদি না-  (ক) বিধি দ্বারা নির্ধারিত ফরমে একজন রেজিস্টার্ড চিকিৎসক কর্তৃক তাহাকে প্রদত্ত সক্ষমতা প্রত্যয়নপত্র মালিকের হেফাজতে থাকে, এবং  (খ) কাজে নিয়োজিত থাকাকালে…

## la06 · single · en · eval
**Q:** How many days of paid annual leave does a factory worker earn?  
**A:** After a year of continuous service, one day for every eighteen days of work in a shop, commercial or industrial establishment, factory or road transport (s.117).  
> **[952:29444] §১১৭ মজুরীসহ বাৎসরিক ছুটি** — ১১৭। (১) কোন প্রতিষ্ঠানে অবিচ্ছিন্নভাবে এক বৎসর চাকুরী পূর্ণ করিয়াছেন এমন প্রত্যেক প্রাপ্ত বয়স্ক শ্রমিককে পরবর্তী বারো মাস সময়ে তাহার পূর্ববর্তী বারো মাসের কাজের জন্য মজুরীসহ নিম্নবর্ণিত হারে গণনার ভিত্তিতে ছুটি মঞ্জুর করিতে হইবে, যথাঃ-  (ক) কোন দোকান বা বাণিজ্য বা শিল্প প্রতিষ্ঠান অথবা কোন কারখানা অথবা সড়ক পরিবহন প্রতিষ্ঠানের ক্ষেত্রে, প্রতি আ…

## la07 · single · mixed · eval
**Q:** Labour Act অনুযায়ী maternity leave কত দিন?  
**A:** প্রসবের আগে ৬০ দিন এবং পরে ৬০ দিন।  
*note:* code-switched  
> **[952:26452] §৪৬ প্রসূতি কল্যাণ সুবিধা প্রাপ্তির অধিকার এবং প্রদানের দায়িত্ব** — ৪৬। (১) প্রত্যেক নারী শ্রমিক তাহার মালিকের নিকট হইতে তাহার সন্তান প্রসবের সম্ভাব্য তারিখের অব্যবহিত পূর্ববর্তী [৬০ (ষাট) দিন] এবং সন্তান প্রসবের অব্যবহিত পরবর্তী [৬০ (ষাট) দিনের] জন্য প্রসূতি কল্যাণ সুবিধা পাইবার অধিকারী হইবেন, এবং তাহার মালিক তাহাকে এই সুবিধা প্রদান করিতে বাধ্য থাকিবেনঃ  তবে শর্ত থাকে যে, কোন নারী উক্তরূপ সুবিধা পাইবেন না যদি না ত…

## ct01 · single · en · eval
**Q:** Is an agreement without consideration valid?  
**A:** It is void, except in listed cases such as a registered written agreement made out of natural love and affection between near relations (s.25).  
> **[26:188] §25 Agreement without consideration void, unless it is in writing and registered, or is a promise to compensate for something done, or is a promise to pay a debt barred by limitation law** — 25. An agreement made without consideration is void, unless–  (1) it is expressed in writing and registered under the law for the time being in force for the registration of documents, and is made on account of natural love and affection between parties standing in a near relation to each other; or unless  (2) it is a promise to compensate, wholly …

## ct02 · single · en · eval
**Q:** Who can legally enter into a contract?  
**A:** A person of the age of majority, of sound mind, and not disqualified by law (s.11).  
> **[26:173] §11 Who are competent to contract** — 11. Every person is competent to contract who is of the age of majority according to the law to which he is subject, and who is of sound mind, and is not disqualified from contracting by any law to which he is subject.…

## ct03 · multi · bn · eval
**Q:** প্রতারণা করে কারও সম্মতি আদায় করা হলে চুক্তির কী হয়?  
**A:** জবরদস্তি, প্রতারণা বা মিথ্যা বর্ণনার মাধ্যমে সম্মতি আদায় হলে চুক্তিটি সংশ্লিষ্ট পক্ষের ইচ্ছায় বাতিলযোগ্য (ধারা ১৯); প্রতারণার সংজ্ঞা ধারা ১৭-এ।  
> **[26:181] §19 Void ability of agreements without free consent** — 19. When consent to an agreement is caused by coercion, fraud or misrepresentation, the agreement is a contract viodable at the option of the party whose consent was so caused.  A party to a contract, whose consent was caused by fraud or misrepresentation, may, if he thinks fit, insist that the contract shall be performed, and that he shall be put …
> **[26:179] §17 "Fraud" defined** — 17. "Fraud" means and includes any of the following acts committed by a party to a contract, or with his connivance, or by his agent, with intent to deceive another party thereto or his agent, or to induce him to enter into the contract:-  (1) the suggestion, as a fact, of that which is not true, by one who does not believe it to be true;  (2) the …

## ct04 · paraphrase · en · eval
**Q:** If I promise my employer never to open a competing business, is that enforceable?  
**A:** Generally no: an agreement restraining anyone from exercising a lawful profession, trade or business is void to that extent, except e.g. on the sale of goodwill (s.27).  
> **[26:190] §27 Agreement in restraint of trade void Saving of agreement not to carry on business of which good- will is sold** — 27. Every agreement by which any one is restrained from exercising a lawful profession, trade or business of any kind, is to that extent void.  Exception 1.–One who sells the good-will of a business may agree with the buyer to refrain from carrying on a similar business, within specified local limits, so long as the buyer, or any person deriving ti…

## ct05 · single · en · tune
**Q:** What compensation can I claim if the other side breaks a contract?  
**A:** Compensation for loss or damage that naturally arose in the usual course of things from the breach, or that the parties knew was likely; not for remote or indirect loss (s.73).  
> **[26:259] §73 Compensation for loss or damage caused by breach of contract** — 73. When a contract has been broken, the party who suffers by such breach is entitled to receive, from the party who has broken the contract, compensation for any loss or damagecaused to him thereby, which naturally arose in the usual course of things from such breach, or which the parties knew, when they made the contract, to be likely to result f…

## ct06 · exact_ref · en · tune
**Q:** What is section 2 of the Contract Act about?  
**A:** The interpretation clause defining proposal, promise, consideration, agreement, contract and related terms.  
> **[26:163] §2 Interpretation-clause** — 2. In this Act the following words and expressions are used in the following senses, unless a contrary intention appears from the context:-  (a) When one person signifies to another his willingness to do or to abstain from doing anything, with a view to obtaining the assent of that other to such act or abstinence, he is said to make a proposal:  (b…

## ct07 · single · mixed · tune
**Q:** Contract Act এ minor এর সাথে চুক্তি valid কিনা?  
**A:** না; চুক্তি করতে সক্ষম হতে হলে সাবালক হতে হয় (ধারা ১১)।  
*note:* code-switched  
> **[26:173] §11 Who are competent to contract** — 11. Every person is competent to contract who is of the age of majority according to the law to which he is subject, and who is of sound mind, and is not disqualified from contracting by any law to which he is subject.…

## ev01 · single · en · tune
**Q:** Who has to prove a fact in court?  
**A:** Whoever wants the court to give judgment on a right or liability that depends on facts he asserts must prove those facts (s.101).  
> **[24:5120] §101 Burden of proof** — 101. Whoever desires any Court to give judgment as to any legal right or liability dependent on the existence of facts which he asserts, must prove that those facts exist.  When a person is bound to prove the existence of any fact, it is said that the burden of proof lies on that person.  Illustrations  (a) A desires a Court to give judgment that B…

## ev02 · single · bn · eval
**Q:** পুলিশের কাছে দেওয়া স্বীকারোক্তি কি আদালতে প্রমাণ হিসেবে ব্যবহার করা যায়?  
**A:** না; পুলিশ কর্মকর্তার কাছে দেওয়া স্বীকারোক্তি অভিযুক্তের বিরুদ্ধে প্রমাণ করা যাবে না (ধারা ২৫)।  
> **[24:4779] §25 Confession to police-officer not to be proved** — 25. No confession made to a police-officer shall be proved as against a person accused of any offence.…

## ev03 · paraphrase · en · eval
**Q:** Can a child be a witness?  
**A:** Yes. All persons are competent to testify unless the court finds that tender years, old age or disease prevents them from understanding questions or giving rational answers (s.118).  
> **[24:5192] §118 Who may testify** — 118. All persons shall be competent to testify unless the Court considers that they are prevented from understanding the questions put to them, or from giving rational answers to those questions, by tender years, extreme old age, disease, whether of body or mind, or any other cause of the same kind.  Explanation.–A lunatic is not incompetent to tes…

## ev04 · single · en · tune
**Q:** Is hearsay allowed as oral evidence?  
**A:** No. Oral evidence must be direct: a witness must have seen, heard or perceived the fact himself (s.60).  
> **[24:4983] §60 Oral evidence must be direct** — 60. Oral evidence must, in all cases whatever, be direct; that is to say-  if it refers to a fact which could be seen, it must be the evidence of a witness who says he saw it;  if it refers to a fact which could be heard, it must be the evidence of a witness who says he heard it;  if it refers to a fact which could be perceived by any other sense o…

## ev05 · exact_ref · bn · eval
**Q:** সাক্ষ্য আইনের ধারা ১০১ কী বলে?  
**A:** যে ব্যক্তি নিজের দাবিকৃত তথ্যের ওপর নির্ভর করে রায় চান, তাকেই সেই তথ্য প্রমাণ করতে হবে — প্রমাণের দায়িত্ব।  
> **[24:5120] §101 Burden of proof** — 101. Whoever desires any Court to give judgment as to any legal right or liability dependent on the existence of facts which he asserts, must prove that those facts exist.  When a person is bound to prove the existence of any fact, it is said that the burden of proof lies on that person.  Illustrations  (a) A desires a Court to give judgment that B…

## cp01 · single · en · eval
**Q:** What is res judicata?  
**A:** A court shall not try a suit or issue that was directly and substantially in issue in a former suit between the same parties, decided by a competent court (s.11 CPC).  
> **[86:13606] §11 Res Judicata** — 11. No Court shall try any suit or issue in which the matter directly and substantially in issue has been directly and substantially in issue in a former suit between the same parties, or between parties under whom they or any of them claim, litigating under the same title, in a court competent to try such subsequent suit or the suit in which such …

## cp02 · paraphrase · bn · eval
**Q:** একই বিষয়ে আগের মামলা চলমান থাকলে নতুন মামলার বিচার কি চলবে?  
**A:** না; একই পক্ষের মধ্যে একই বিষয়ে আগে দায়ের করা মামলা চলমান থাকলে আদালত পরের মামলার বিচার অগ্রসর করবে না (ধারা ১০)।  
> **[86:13605] §10 Stay of suit** — 10. No Court shall proceed with the trial of any suit in which the matter in issue is also directly and substantially in issue in a previously instituted suit between the same parties, or between parties under whom they or any of them claim litigating under the same title where such suit is pending in the same or any other Court in Bangladesh havin…

## cp03 · exact_ref · en · tune
**Q:** What does section 9 of the Code of Civil Procedure provide?  
**A:** Civil courts have jurisdiction to try all suits of a civil nature unless their cognizance is expressly or impliedly barred.  
> **[86:13604] §9 Courts to try all civil suits unless barred** — 9. The Courts shall (subject to the provisions herein contained) have jurisdiction to try all suits of a civil nature excepting suits of which their cognizance is either expressly or impliedly barred.  Explanation.-A suit in which the right to property or to an office is contested is a suit of a civil nature, notwithstanding that such right may dep…

## tp01 · single · en · eval
**Q:** What is a mortgage under the law?  
**A:** The transfer of an interest in specific immovable property to secure payment of a loan, a debt, or an engagement that may create a pecuniary liability (s.58).  
> **[48:26415] §58 “Mortgage,” “mortgagor,” “mortgagee,” “mortgage-money” and “mortgage-deed”defined** — 58. (a) A mortgage is the transfer of an interest in specific immoveable property for the purpose of securing the payment of money advanced or to be advanced by way of loan, an existing or future debt, or the performance of an engagement which may give rise to a pecuniary liability.The transferor is called a mortgagor, the transferee a mortgagee; t…

## tp02 · single · en · eval
**Q:** What is a lease of immovable property?  
**A:** A transfer of a right to enjoy immovable property for a certain time or in perpetuity, in return for a price paid or promised or periodic rent (s.105).  
> **[48:16320] §105 “Lease” defined** — 105. A lease of immoveable property is a transfer of a right to enjoy such property, made for a certain time, express or implied, or in perpetuity, in consideration of a price paid or promised, or of money, a share of crops, service or any other thing of value, to be rendered periodically or on specified occasions to the transferor by the transfere…

## ns01 · multi · bn · tune
**Q:** ধর্ষণের শাস্তি কী?  
**A:** নারী ও শিশু নির্যাতন দমন আইনে ধর্ষণের শাস্তি মৃত্যুদণ্ড বা যাবজ্জীবন সশ্রম কারাদণ্ড এবং অর্থদণ্ড (ধারা ৯); দণ্ডবিধির ধারা ৩৭৬-এও শাস্তির বিধান আছে।  
> **[835:32523] §৯ ধর্ষণ, ধর্ষণজনিত কারণে মৃত্যু, ইত্যাদির শাস্তি** — ৯। [(১) যদি কোন ব্যক্তি কোন নারী বা শিশুকে ধর্ষণ করেন, তাহা হইলে তিনি মৃত্যুদণ্ডে বা যাবজ্জীবন সশ্রম কারাদণ্ডে দণ্ডনীয় হইবেন এবং ইহার অতিরিক্ত অর্থদণ্ডেও দণ্ডনীয় হইবেন।  ব্যাখ্যা।- (১) যদি কোন ব্যক্তি বিবাহ বন্ধন ব্যতীত ষোল বৎসরের অধিক বয়সের কোন নারীর সহিত তাহার সম্মতি ব্যতিরেকে বা ভীতি প্রদর্শন করিয়া বা প্রতারণামূলকভাবে তাহার সম্মতি আদায় করিয…
> **[11:3232] §376 Punishment for rape** — 376. Whoever commits rape shall be punished with [imprisonment] for life or with imprisonment of either description for a term which may extend to ten years, and shall also be liable to fine, unless the woman raped is his own wife and is not under twelve years of age, in which case he shall be punished with imprisonment of either description for a …

## ns02 · single · bn · tune
**Q:** যৌতুকের জন্য স্ত্রীকে হত্যা করলে কী শাস্তি হয়?  
**A:** যৌতুকের জন্য মৃত্যু ঘটালে মৃত্যুদণ্ড বা যাবজ্জীবন সশ্রম কারাদণ্ড এবং অর্থদণ্ড (নারী ও শিশু নির্যাতন দমন আইন, ধারা ১১(ক))।  
> **[835:32526] §১১ যৌতুকের জন্য মৃত্যু ঘটানো, ইত্যাদির শাস্তি** — ১১। যদি কোন নারীর স্বামী অথবা স্বামীর পিতা, মাতা, অভিভাবক, আত্মীয় বা স্বামীর পক্ষে অন্য কোন ব্যক্তি যৌতুকের জন্য উক্ত নারীর মৃত্যু ঘটান বা মৃত্যু ঘটানোর চেষ্টা করেন [কিংবা উক্ত নারীকে মারাত্মক জখম (grievous hurt) করেন বা সাধারণ জখম (simple hurt) করেন] তাহা হইলে উক্ত স্বামী, স্বামীর পিতা, মাতা, অভিভাবক, আত্মীয় বা ব্যক্তি-  [(ক) মৃত্যু ঘটানোর জন্য …

## ns03 · single · en · eval
**Q:** What is the punishment for kidnapping a woman or child?  
**A:** Imprisonment for life or rigorous imprisonment of not less than fourteen years, and fine (s.7).  
> **[835:32521] §৭ নারী ও শিশু অপহরণের শাস্তি** — ৭। যদি কোন ব্যক্তি [মানব পাচার প্রতিরোধ ও দমন আইন, ২০১২ (২০১২ সনের ৩ নং আইন) এর ধারা ৩ ও ৬ এ উল্লিখিত] কোন অপরাধ সংঘটনের উদ্দেশ্য ব্যতীত অন্য কোন উদ্দেশ্যে কোন নারী বা শিশুকে অপহরণ করেন, তাহা হইলে উক্ত ব্যক্তি যাবজ্জীবন কারাদণ্ডে বা অন্যূন চৌদ্দ বৎসর সশ্রম কারাদণ্ডে দণ্ডনীয় হইবেন এবং ইহার অতিরিক্ত অর্থদণ্ডেও দণ্ডনীয় হইবেন।…

## cn01 · single · bn · eval
**Q:** ভেজাল পণ্য বিক্রি করলে কী শাস্তি হয়?  
**A:** অনূর্ধ্ব তিন বৎসর কারাদণ্ড, বা অনধিক দুই লক্ষ টাকা অর্থদণ্ড, বা উভয় দণ্ড (ধারা ৪১)।  
> **[1014:39149] §৪১ ভেজাল পণ্য বা ঔষধ বিক্রয়ের দণ্ড** — ৪১। কোন ব্যক্তি জ্ঞাতসারে ভেজাল মিশ্রিত পণ্য বা ঔষধ বিক্রয় করিলে বা করিতে প্রস্তাব করিলে তিনি অনূর্ধ্ব তিন বৎসর কারাদণ্ড, বা অনধিক দুই লক্ষ টাকা অর্থদণ্ড, বা উভয় দণ্ডে দণ্ডিত হইবেন।…

## cn02 · single · en · eval
**Q:** What is the penalty for selling goods above the fixed price?  
**A:** Up to one year's imprisonment, or a fine of up to fifty thousand taka, or both (s.40).  
> **[1014:39148] §৪০ ধার্য্যকৃত মূল্যের অধিক মূল্যে পণ্য, ঔষধ বা সেবা বিক্রয় করিবার দণ্ড** — ৪০। কোন ব্যক্তি কোন আইন বা বিধির অধীন নির্ধারিত মূল্য অপেক্ষা অধিক মূল্যে কোন পণ্য, ঔষধ বা সেবা বিক্রয় বা বিক্রয়ের প্রস্তাব করিলে তিনি অনূর্ধ্ব এক বৎসর কারাদণ্ড, বা অনধিক পঞ্চাশ হাজার টাকা অর্থদণ্ড, বা উভয় দণ্ডে দণ্ডিত হইবেন।…

## cn03 · single · bn · eval
**Q:** ভোক্তা কোথায় অভিযোগ করতে পারেন?  
**A:** মহাপরিচালক বা তার কাছ থেকে ক্ষমতাপ্রাপ্ত ব্যক্তির কাছে লিখিত অভিযোগ করা যায় (ধারা ৭৬)।  
> **[1014:39187] §৭৬ অভিযোগ এবং জরিমানার টাকায় অভিযোগকারীর অংশ** — ৭৬। (১) যে কোন ব্যক্তি, যিনি, সাধারণভাবে একজন ভোক্তা বা ভোক্তা হইতে পারেন, এই অধ্যাদেশের অধীন ভোক্তা-অধিকার বিরোধী কার্য সম্পর্কে মহাপরিচালক বা এতদুদ্দেশ্যে মহাপরিচালকের নিকট হইতে ক্ষমতাপ্রাপ্ত ব্যক্তিকে অবহিত করিয়া লিখিত অভিযোগ দায়ের করিতে পারিবেন।  (২) কর্তৃপক্ষ, উপ-ধারা (১) এর অধীন লিখিত অভিযোগ প্রাপ্তির পর, অনতিবিলম্বে অভিযোগটি অনুসন্ধান বা ত…

## cn04 · paraphrase · bn · eval
**Q:** দোকানদার ওজনে কম দিলে কী শাস্তি হয়?  
**A:** ওজন পরিমাপক যন্ত্রে কারচুপির জন্য অনূর্ধ্ব এক বৎসর কারাদণ্ড বা অর্থদণ্ড বা উভয় দণ্ড (ধারা ৪৭)।  
> **[1014:39155] §৪৭ বাটখারা বা ওজন পরিমাপক যন্ত্রে কারচুপির দণ্ড** — ৪৭। কোন পণ্য বিক্রয় বা সরবরাহের উদ্দেশ্যে কোন ব্যক্তির দোকান বা ব্যবসা প্রতিষ্ঠানে ওজন পরিমাপের কার্যে ব্যবহৃত বাটখারা বা ওজন পরিমাপক যন্ত্র প্রকৃত ওজন অপেক্ষা অতিরিক্ত ওজন প্রদর্শনকারী হইলে তিনি অনূর্ধ্ব এক বৎসর কারাদণ্ড, বা অনধিক পঞ্চাশ হাজার টাকা অর্থদণ্ড, বা উভয় দণ্ডে দণ্ডিত হইবেন।…

## rt01 · single · bn · eval
**Q:** বাড়িওয়ালা কি ভাড়ার অতিরিক্ত সালামি বা জামানত নিতে পারেন?  
**A:** না; ভাড়ার অতিরিক্ত কোনো প্রিমিয়াম, সালামি বা জামানত দাবি বা গ্রহণ করা যাবে না, এবং অগ্রিম হিসেবে এক মাসের ভাড়ার বেশি নেওয়া যাবে না (ধারা ১০)।  
> **[748:30640] §১০ প্রিমিয়াম ইত্যাদির দাবী নিষিদ্ধ** — ১০। ভাড়া দেওয়া বা ভাড়া নবায়ন করা বা ভাড়ার মেয়াদ বৃদ্ধি করার কারণে কোন ব্যক্তি-  (ক) ভাড়ার অতিরিক্ত কোন প্রিমিয়াম, সালামী, জামানত বা অনুরূপ কোন অর্থ দাবী বা গ্রহণ করিতে বা প্রদানের জন্য বলিতে পারিবেন না, অথবা  (খ) নিয়ন্ত্রকের পূর্বানুমোদন ব্যতিরেকে, অগ্রীম ভাড়া হিসাবে এক মাসের ভাড়ার অতিরিক্ত টাকা দাবী বা গ্রহণ করিতে পারিবেন না।…

## rt02 · single · bn · eval
**Q:** ভাড়াটিয়া নিয়মিত ভাড়া দিলে কি তাকে উচ্ছেদ করা যায়?  
**A:** সাধারণত না; ভাড়াটিয়া অনুমোদনযোগ্য ভাড়া পুরোপুরি পরিশোধ ও শর্ত মেনে চললে উচ্ছেদের আদেশ দেওয়া যাবে না, আইনে উল্লিখিত ব্যতিক্রম ছাড়া (ধারা ১৮)।  
> **[748:30648] §১৮ অনুমোদনযোগ্য ভাড়া প্রদান করা হইলে সাধারণতঃ উচ্ছেদের আদেশ দেওয়া হইবে না** — ১৮। (১) Transfer of Property Act, 1882 (IV of 1882) অথবা Contract Act, 1872 (IX of 1872) এ যাহা কিছুই থাকুক না কেন, কোন ভাড়াটিয়া এই আইনের অধীন অনুমোদনযোগ্য ভাড়া যতদিন পর্যন্ত পূর্ণমাত্রায় আদায় করিবেন এবং ভাড়ার শর্তাদি পূরণ করিবেন ততদিন পর্যন্ত বাড়ী-মালিকের অনুকূলে বাড়ীর দখল পুনরুদ্ধারের জন্য কোন আদেশ বা ডিক্রি প্রদান করা যাইবে না :  তবে শর্…

## rt03 · paraphrase · en · tune
**Q:** Does my landlord have to give me a receipt when I pay rent?  
**A:** Yes. The landlord must immediately give a signed receipt in the prescribed form and keep a counterfoil (s.13, Premises Rent Control Act 1991).  
> **[748:30643] §১৩ ভাড়া আদায়ের রশিদ প্রদান** — ১৩। (১) ভাড়াটিয়া কর্তৃক ভাড়া পরিশোধ করা হইলে বাড়ী-মালিক তৎক্ষণাৎ ভাড়া প্রাপ্তির একটি রশিদ বিধি দ্বারা নির্ধারিত ফরমে স্বাক্ষর করিয়া ভাড়াটিয়াকে প্রদান করিবেন।  (২) বাড়ী-মালিক ভাড়ার রশিদের একটি চেকমুড়ি সংরক্ষণ করিবেন।…

## rt04 · single · en · eval
**Q:** Who fixes the standard rent of a house?  
**A:** The Rent Controller, on the application of the landlord or tenant (s.15).  
> **[748:30645] §১৫ নিয়ন্ত্রকের ক্ষমতা ও দায়িত্ব** — ১৫। নিয়ন্ত্রক, বাড়ী-মালিক বা ভাড়াটিয়ার আবেদনের ভিত্তিতে, কোন বাড়ীর মানসম্মত ভাড়া নির্ধারণ করিবেন এবং এমনভাবে উহা নির্ধারণ করিবেন যেন উহার বাৎসরিক পরিমাণ বিধি দ্বারা নির্ধারিত পদ্ধতিতে স্থিরকৃত উক্ত বাড়ীর বাজার মূল্যের ১৫% শতাংশের সমান হয় :  তবে শর্ত থাকে যে, যেক্ষেত্রে মানসম্মত ভাড়ার পরিমাণ Premises Rent Control Ordinance, 1986 (XXII of 19…

## rg01 · single · en · eval
**Q:** Which documents must be registered compulsorily?  
**A:** Among others: gift deeds of immovable property, non-testamentary instruments creating or transferring interests in immovable property of value, leases above a year, and the other documents listed in s.17.  
> **[90:22917] §17 Documents of which registration is compulsory** — 17. (1) The following documents shall be registered, if the property to which they relate is situate in a district in which, and if they have been executed on or after the date on which, [* * *] this Act came or comes into force, namely:-  (a) instruments of gift of immoveable property;  [(aa) declaration of heba under the Muslim Personal Law (Shar…

## rg02 · single · en · eval
**Q:** Within how long must a document be presented for registration?  
**A:** Within three months from the date of its execution, subject to sections 24–26; wills excepted (s.23).  
> **[90:22926] §23 Time for presenting documents** — 23. Subject to the provisions contained in sections 24, 25 and 26, no document other than a will shall be accepted for registration unless presented for that purpose to the proper officer within [three months] from the date of its execution:  Provided that a copy of a decree or order may be presented within [three months] from the day on which the …

## ni01 · single · en · eval
**Q:** What happens if a cheque bounces?  
**A:** If a cheque is returned unpaid for insufficient funds, the drawer commits an offence punishable with up to one year's imprisonment, or a fine up to thrice the cheque amount, or both — provided the cheque was presented in time, notice was given and payment was not made (s.138).  
> **[46:1519] §138 Dishonour of cheque for insufficiency, etc. of funds in the account** — 138. [(1)] Where any cheque drawn by a person on an account maintained by him with a banker for payment of any amount of money to another person from out of that account [* * *] is returned by the bank unpaid, either because of the amount of money standing to the credit of that account is insufficient to honour the cheque or that it exceeds the amo…

## ni02 · multi · mixed · eval
**Q:** চেক ডিসঅনার মামলা কীভাবে ও কখন দায়ের করতে হয়?  
**A:** প্রাপক বা যথাযথ ধারক লিখিত অভিযোগ করবেন, এবং তা ধারা ১৩৮-এর শর্ত অনুযায়ী মামলার কারণ উদ্ভবের এক মাসের মধ্যে (ধারা ১৪১); অপরাধের উপাদান ধারা ১৩৮-এ।  
> **[46:1523] §141 Cognizance of offences** — 141. Notwithstanding anything contained in the Code of Criminal Procedure, 1898 (Act V of 1898),-  (a) no court shall take cognizance of any offence punishable under section 138 except upon a complaint, in writing, made by the payee or, as the case may be, the holder in due course of the cheque;  (b) such complaint is made within one month of the d…
> **[46:1519] §138 Dishonour of cheque for insufficiency, etc. of funds in the account** — 138. [(1)] Where any cheque drawn by a person on an account maintained by him with a banker for payment of any amount of money to another person from out of that account [* * *] is returned by the bank unpaid, either because of the amount of money standing to the credit of that account is insufficient to honour the cheque or that it exceeds the amo…

## mf01 · single · en · eval
**Q:** Can a Muslim man take a second wife without permission?  
**A:** No. He needs the prior written permission of the Arbitration Council (s.6, Muslim Family Laws Ordinance 1961).  
> **[305:13538] §6 Polygamy** — 6. (1) No man, during the subsistence of an existing marriage, shall, except with the previous permission in writing of the Arbitration Council, contract another marriage, nor shall any such marriage contracted without such permission be registered [under the Muslim Marriages and Divorces (Registration) Act, 1974 (LII of 1974)].  (2) An application…

## mf02 · single · bn · eval
**Q:** তালাক দেওয়ার পর স্বামীকে কী করতে হয়?  
**A:** তালাক উচ্চারণের পর যত শীঘ্র সম্ভব চেয়ারম্যানকে লিখিত নোটিশ দিতে হয় এবং স্ত্রীকে তার একটি কপি দিতে হয় (ধারা ৭)।  
> **[305:13539] §7 Talaq** — 7. (1) Any man who wishes to divorce his wife shall, as soon as may be after the pronouncement of talaq in any form whatsoever, give the Chairman notice in writing of his having done so, and shall supply a copy thereof to the wife.  (2) Whoever contravenes the provisions of sub-section (1) shall be punishable with simple imprisonment for term which…

## mf03 · single · en · eval
**Q:** What can a wife do if her husband does not maintain her?  
**A:** She may apply to the Chairman, who sets up an Arbitration Council to fix the maintenance amount (s.9).  
> **[305:13541] §9 Maintenance** — 9. (1) If any husband fails to maintain his wife adequately, or where there are more wives than one, fails to maintain them equitably, the wife, or all or any of the wives, may in addition to seeking, any other legal remedy available apply to the Chairman who shall constitute an Arbitration Council to determine the matter, and the Arbitration Counc…

## dw01 · single · bn · eval
**Q:** যৌতুক দাবি করলে কী শাস্তি হয়?  
**A:** অনধিক ৫ বৎসর কিন্তু অন্যূন ১ বৎসর কারাদণ্ড বা অনধিক ৫০ হাজার টাকা অর্থদণ্ড বা উভয় দণ্ড (ধারা ৩)।  
> **[1256:47647] §৩ যৌতুক দাবি করিবার দণ্ড** — ৩। যদি বিবাহের কোনো এক পক্ষ, প্রত্যক্ষ বা পরোক্ষভাবে, বিবাহের অন্য কোনো পক্ষের নিকট কোনো যৌতুক দাবি করেন, তাহা হইলে উহা হইবে এই আইনের অধীন একটি অপরাধ এবং তজ্জন্য তিনি অনধিক ৫ (পাঁচ) বৎসর কিন্তু অন্যূন ১ (এক) বৎসর কারাদণ্ড বা অনধিক ৫০,০০০ (পঞ্চাশ হাজার) টাকা অর্থদণ্ড অথবা উভয় দণ্ডে দণ্ডনীয় হইবেন।…

## dw02 · single · en · eval
**Q:** What counts as dowry under the Dowry Prohibition Act 2018?  
**A:** Money or property demanded or given, directly or indirectly, by one party to a marriage from the other as a condition of the marriage, as defined in s.2.  
> **[1256:47646] §২ সংজ্ঞা** — ২। বিষয় বা প্রসঙ্গের পরিপন্থি কোনো কিছু না থাকিলে,-  (ক) ‘‘পক্ষ’’ অর্থ এই আইনের উদ্দেশ্য পূরণকল্পে, বিবাহের বর বা কনে অথবা বর বা কনের পিতা-মাতা অথবা বর বা কনের পিতা-মাতার অবর্তমানে বৈধ অভিভাবক অথবা প্রত্যক্ষভাবে বিবাহের সহিত জড়িত বর বা কনে পক্ষের অন্য কোনো ব্যক্তি; এবং  (খ) ‘‘যৌতুক’’ অর্থ বিবাহের এক পক্ষ কর্তৃক অন্য পক্ষের নিকট বৈবাহিক সম্পর্ক স্…

## cm01 · single · bn · eval
**Q:** বাল্যবিবাহ করলে কী শাস্তি হয়?  
**A:** প্রাপ্তবয়স্ক নারী বা পুরুষ বাল্যবিবাহ করলে অনধিক ২ বৎসর কারাদণ্ড বা অনধিক ১ লক্ষ টাকা অর্থদণ্ড বা উভয় দণ্ড (ধারা ৭)।  
> **[1207:45736] §৭ বাল্যবিবাহ করিবার শাস্তি** — ৭। (১) প্রাপ্ত বয়স্ক কোন নারী বা পুরুষ বাল্যবিবাহ করিলে উহা হইবে একটি অপরাধ এবং তজ্জন্য তিনি অনধিক ২ (দুই) বৎসর কারাদণ্ড বা অনধিক ১ (এক) লক্ষ টাকা অর্থদণ্ড বা উভয় দণ্ডে দণ্ডনীয় হইবেন এবং অর্থদণ্ড অনাদায়ে অনধিক ৩ (তিন) মাস কারাদণ্ডে দণ্ডনীয় হইবেন।  (২) অপ্রাপ্ত বয়স্ক কোন নারী বা পুরুষ বাল্যবিবাহ করিলে তিনি অনধিক ১ (এক) মাসের আটকাদেশ বা অনধিক ৫…

## cm02 · single · en · eval
**Q:** What is the legal age of marriage for girls and boys?  
**A:** A man under 21 and a woman under 18 are minors for the purpose of marriage (s.2).  
> **[1207:45731] §২ সংজ্ঞা** — ২। বিষয় বা প্রসঙ্গের পরিপন্থি কিছু না থাকিলে, এই আইনে-  (১) “অপ্রাপ্ত বয়স্ক” অর্থ বিবাহের ক্ষেত্রে ২১ (একুশ) বৎসর পূর্ণ করেন নাই এমন কোনো পুরুষ এবং ১৮ (আঠারো) বৎসর পূর্ণ করেন নাই এমন কোনো নারী;  (২) “অভিভাবক” অর্থ Guardians and Wards Act, 1890 (Act No. VIII of 1890) এর অধীন নিয়োগপ্রাপ্ত বা ঘোষিত অভিভাবক এবং অপ্রাপ্ত বয়স্ক ব্যক্তির ভরণ-পোষণ বহনক…

## ri01 · single · bn · eval
**Q:** তথ্য অধিকার আইনে আবেদন করলে কত দিনের মধ্যে তথ্য দিতে হয়?  
**A:** অনুরোধ প্রাপ্তির তারিখ থেকে অনধিক ২০ কার্যদিবসের মধ্যে (ধারা ৯)।  
> **[1011:39081] §৯ তথ্য প্রদান পদ্ধতি** — ৯। (১) দায়িত্বপ্রাপ্ত কর্মকর্তা ধারা ৮ এর উপ-ধারা (১) এর অধীন অনুরোধ প্রাপ্তির তারিখ হইতে অনধিক ২০ (বিশ) কার্য দিবসের মধ্যে অনুরোধকৃত তথ্য সরবরাহ করিবেন।  (২) উপ-ধারা (১) এ যাহা কিছুই থাকুক না কেন, অনুরোধকৃত তথ্যের সহিত একাধিক তথ্য প্রদান ইউনিট বা কর্তৃপক্ষের সংশ্লিষ্টতা থাকিলে অনধিক ৩০ (ত্রিশ) কার্য দিবসের মধ্যে উক্ত অনুরোধকৃত তথ্য সরবরাহ করিতে হ…

## ri02 · single · en · tune
**Q:** Which information can an authority refuse to give under the RTI Act?  
**A:** Information listed in s.7, e.g. that which would threaten national security, integrity or sovereignty, impede investigations, or breach privacy.  
> **[1011:39079] §৭ কতিপয় তথ্য প্রকাশ বা প্রদান বাধ্যতামূলক নয়** — ৭। এই আইনের অন্যান্য বিধানাবলীতে যাহা কিছুই থাকুক না কেন, কোন কর্তৃপক্ষ কোন নাগরিককে নিম্নলিখিত তথ্যসমূহ প্রদান করিতে বাধ্য থাকিবে না, যথাঃ -  (ক) কোন তথ্য প্রকাশের ফলে বাংলাদেশের নিরাপত্তা, অখণ্ডতা ও সার্বভৌমত্বের প্রতি হুমকি হইতে পারে এইরূপ তথ্য;  (খ) পররাষ্ট্রনীতির কোন বিষয় যাহার দ্বারা বিদেশী রাষ্ট্রের অথবা আন্তর্জাতিক কোন সংস্থা বা আঞ্চলিক কো…

## ri03 · single · mixed · eval
**Q:** RTI আবেদন করে কত দিনে তথ্য পাব?  
**A:** অনধিক ২০ কার্যদিবসের মধ্যে।  
*note:* code-switched  
> **[1011:39081] §৯ তথ্য প্রদান পদ্ধতি** — ৯। (১) দায়িত্বপ্রাপ্ত কর্মকর্তা ধারা ৮ এর উপ-ধারা (১) এর অধীন অনুরোধ প্রাপ্তির তারিখ হইতে অনধিক ২০ (বিশ) কার্য দিবসের মধ্যে অনুরোধকৃত তথ্য সরবরাহ করিবেন।  (২) উপ-ধারা (১) এ যাহা কিছুই থাকুক না কেন, অনুরোধকৃত তথ্যের সহিত একাধিক তথ্য প্রদান ইউনিট বা কর্তৃপক্ষের সংশ্লিষ্টতা থাকিলে অনধিক ৩০ (ত্রিশ) কার্য দিবসের মধ্যে উক্ত অনুরোধকৃত তথ্য সরবরাহ করিতে হ…

## lm01 · single · en · eval
**Q:** What happens to a case filed after the limitation period?  
**A:** It shall be dismissed, even if limitation has not been set up as a defence (s.3, Limitation Act).  
> **[88:6445] §3 Dismissal of suits, etc., instituted, etc., after period of limitation** — 3. Subject to the provisions contained in sections 4 to 25 (inclusive), every suit instituted, appeal preferred, and application made, after the period of limitation prescribed therefor by the first schedule shall be dismissed, although limitation has not been set up as a defence.  Explanation.-A suit is instituted, in ordinary cases, when the plai…

## lm02 · paraphrase · en · tune
**Q:** Can a court accept an appeal filed late?  
**A:** Yes, if the appellant satisfies the court that he had sufficient cause for not filing within the period (s.5).  
> **[88:6447] §5 Extension of period in certain cases** — 5. Any appeal or application for a revision or a review of judgment or for leave to appeal or any other application to which this section may be made applicable by or under any enactment for the time being in force may be admitted after the period of limitation prescribed therefor, when the appellant or applicant satisfies the Court that he had suf…

## sr01 · single · en · eval
**Q:** Can a court force someone to perform a contract instead of paying damages?  
**A:** Yes, specific performance may be enforced at the court's discretion in the cases in s.12, e.g. where money compensation would not be adequate relief.  
> **[36:24723] §12 Cases in which specific performance enforceable** — 12. Except as otherwise provided in this Chapter, the specific performance of any contract may in the discretion of the Court be enforced-  (a) when the act agreed to be done is in the performance, wholly or partly, of a trust;  (b) when [there] exists no standard for ascertaining the actual damage caused by non-performance of the act agreed to be …

## sr02 · paraphrase · en · eval
**Q:** Someone threw me out of my land without legal process. Can I get it back quickly?  
**A:** Yes. A person dispossessed of immovable property without consent and otherwise than in due course of law may sue to recover possession, whatever other title is set up; no appeal lies from the decree (s.9).  
> **[36:24720] §9 Suit by person dispossessed of immoveable property** — 9. If any person is dispossessed without his consent of immoveable property otherwise than in due course of law, he or any person claiming through him may, by suit recover possession thereof, notwithstanding any other title that may be set up in such suit.  Nothing in this section shall bar any person from suing to establish his title to such prope…

## fc01 · single · bn · eval
**Q:** পারিবারিক আদালত কোন কোন বিষয়ে মামলা শুনতে পারে?  
**A:** বিবাহ বিচ্ছেদ, দাম্পত্য অধিকার পুনরুদ্ধার, দেনমোহর, ভরণপোষণ এবং অভিভাবকত্ব ও সন্তানের হেফাজত সংক্রান্ত মামলা (ধারা ৫)।  
> **[1444:52391] §৫ পারিবারিক আদালতের এখতিয়ার** — ৫। মুসলিম পারিবারিক আইনের বিধানাবলি সাপেক্ষে, পারিবারিক আদালতে নিম্নরূপ সকল বা যেকোনো বিষয় সম্পর্কিত বা উহা হইতে উদ্ভূত যেকোনো মোকদ্দমা গ্রহণ, বিচার এবং নিষ্পত্তির এখতিয়ার থাকিবে, যথা :-  (ক) বিবাহ বিচ্ছেদ;  (খ) দাম্পত্য অধিকার পুনরুদ্ধার;  (গ) দেনমোহর;  (ঘ) ভরণপোষণ; এবং  (ঙ) শিশু সন্তানদের অভিভাবকত্ব ও তত্ত্বাবধান।…

## en01 · single · bn · eval
**Q:** পলিথিন শপিং ব্যাগ কি নিষিদ্ধ করা যায়?  
**A:** হ্যাঁ; সরকার পরিবেশের জন্য ক্ষতিকর মনে করলে প্রজ্ঞাপন দিয়ে পলিথিন শপিং ব্যাগ উৎপাদন, বিক্রয় ইত্যাদি নিষিদ্ধ করতে পারে (ধারা ৬ক)।  
> **[791:28760] §৬ক পরিবেশের জন্য ক্ষতিকর সামগ্রী উৎপাদন, বিক্রয় ইত্যাদির উপর বাধা-নিষেধ** — [৬ক। সরকার, মহা-পরিচালকের পরামর্শ বা অন্য কোনভাবে যদি সন্তুষ্ট হয় যে, সকল বা যে কোন প্রকার পলিথিন শপিং ব্যাগ, বা পলিইথাইলিন বা পলিপ্রপাইলিনের তৈরী অন্য কোন সামগ্রী বা অন্য যে কোন সামগ্রী পরিবেশের জন্য ক্ষতিকর, তাহা হইলে, সরকারী গেজেটে প্রজ্ঞাপন দ্বারা, সমগ্র দেশে বা কোন নির্দিষ্ট এলাকায় এইরূপ সামগ্রীর উৎপাদন, আমদানী, বাজারজাতকরণ, বিক্রয়, বিক্রয়…

## en02 · single · en · eval
**Q:** Do I need environmental clearance to set up a factory?  
**A:** Yes. No industrial unit or project may be established without an environmental clearance certificate from the Director General (s.12).  
> **[791:28766] §১২ পরিবেশগত ছাড়পত্র** — [১২। (১) মহা-পরিচালকের নিকট হইতে, বিধি দ্বারা নির্ধারিত পদ্ধতিতে, পরিবেশগত ছাড়পত্র ব্যতিরেকে কোন এলাকায় কোন শিল্প প্রতিষ্ঠান স্থাপন বা প্রকল্প গ্রহণ করা যাইবে না।  (২) এই আইন কার্যকর হইবার অব্যবহিত পূর্বে স্থাপিত শিল্প প্রতিষ্ঠান বা গৃহীত প্রকল্পের ক্ষেত্রে, বাংলাদেশ পরিবেশ সংরক্ষণ (সংশোধন) আইন, ২০১০ কার্যকরের পর অবিলম্বে পরিবেশগত ছাড়পত্র গ্রহণ …

## br01 · single · bn · eval
**Q:** জন্মের কত দিনের মধ্যে জন্ম নিবন্ধনের তথ্য দিতে হয়?  
**A:** শিশুর জন্মের ৪৫ দিনের মধ্যে (ধারা ৮)।  
> **[921:27686] §৮ জন্ম ও মৃত্যু তথ্য প্রদানের জন্য দায়ী ব্যক্তি** — ৮। (১) শিশুর পিতা বা মাতা বা অভিভাবক বা নির্ধারিত ব্যক্তি উক্ত শিশুর জন্মের ৪৫ (পঁয়তাল্লিশ) দিনের মধ্যে জন্ম সংক্রান্ত তথ্য নিবন্ধকের নিকট প্রদানের জন্য বাধ্য থাকিবেন।  (২) মৃত ব্যক্তির পুত্র বা কন্যা বা অভিভাবক বা নির্ধারিত ব্যক্তি মৃত্যুর [৪৫ (পঁয়তাল্লিশ)] দিনের মধ্যে মৃত্যু সংক্রান্ত তথ্য নিবন্ধকের নিকট প্রদানের জন্য বাধ্য থাকিবেন।…

## po01 · single · bn · eval
**Q:** পর্নোগ্রাফি উৎপাদনের শাস্তি কী?  
**A:** অনধিক ৭ বৎসর সশ্রম কারাদণ্ড এবং অনধিক ২ লক্ষ টাকা অর্থদণ্ড (ধারা ৮(১))।  
> **[1091:41881] §৮ দণ্ড** — ৮। (১) কোন ব্যক্তি পর্নোগ্রাফি উৎপাদন করিলে বা উৎপাদন করিবার জন্য অংশগ্রহণকারী সংগ্রহ করিয়া চুক্তিপত্র করিলে অথবা কোন নারী, পুরুষ বা শিশুকে অংশগ্রহণ করিতে বাধ্য করিলে অথবা কোন নারী, পুরুষ বা শিশুকে কোন প্রলোভনে অংশগ্রহণ করাইয়া তাহার জ্ঞাতে বা অজ্ঞাতে স্থির চিত্র, ভিডিও চিত্র বা চলচ্চিত্র ধারণ করিলে তিনি অপরাধ করিয়াছেন বলিয়া গণ্য হইবেন এবং উক্তর…

## ac01 · single · bn · eval
**Q:** এসিড নিক্ষেপ করে কারও মৃত্যু ঘটালে কী শাস্তি?  
**A:** মৃত্যুদণ্ড বা যাবজ্জীবন সশ্রম কারাদণ্ড এবং অনূর্ধ্ব এক লক্ষ টাকা অর্থদণ্ড (ধারা ৪)।  
> **[883:27421] §৪ এসিড দ্বারা মৃত্যু ঘটানোর শাস্তি** — ৪। যদি কোন ব্যক্তি এসিড দ্বারা অন্য কোন ব্যক্তির মৃত্যু ঘটান তাহা হইলে উক্ত ব্যক্তি মৃত্যুদণ্ডে বা যাবজ্জীবন সশ্রম কারাদণ্ডে দণ্ডনীয় হইবেন এবং ইহার অতিরিক্ত অনূর্ধ্ব এক লক্ষ টাকা অর্থদণ্ডেও দণ্ডনীয় হইবেন।…

## ch01 · single · en · eval
**Q:** Who counts as a child under the Children Act 2013?  
**A:** Every person up to the age of 18 years (s.4).  
> **[1119:42716] §৪ শিশু** — ৪। বিদ্যমান অন্য কোন আইনে ভিন্নতর যাহা কিছুই থাকুক না কেন, এই আইনের উদ্দেশ্যপূরণকল্পে, অনুর্ধ্ব ১৮ (আঠার) বৎসর বয়স পর্যন্ত সকল ব্যক্তি শিশু হিসাবে গণ্য হইবে।…

## ch02 · single · bn · eval
**Q:** শিশুকে কি মৃত্যুদণ্ড দেওয়া যায়?  
**A:** না; কোনো শিশুকে মৃত্যুদণ্ড, যাবজ্জীবন কারাদণ্ড বা কারাদণ্ড দেওয়া যাবে না (ধারা ৩৩(১))।  
> **[1119:42745] §৩৩ শিশুর ওপর নির্দিষ্ট ধরনের দণ্ড আরোপে বাধা-নিষেধ** — ৩৩। (১) অন্য কোন আইনে ভিন্নরূপ যাহা কিছুই থাকুক না কেন, কোন শিশুকে মৃত্যুদণ্ড, যাবজ্জীবন কারাদণ্ড বা কারাদণ্ড প্রদান করা যাইবে না :  তবে শর্ত থাকে যে, কোন শিশুকে যখন এইরূপ কোন মারাত্নক ধরনের অপরাধ সংঘটন করিতে দেখা যায় যে, তজ্জন্য এই আইনের অধীন প্রদানযোগ্য কোন আটকাদেশ আদালতের মতে পর্যাপ্ত নহে, অথবা আদালত যদি এই মর্মে সন্তুষ্ট হয় যে শিশুটি এত বেশি …

## mc01 · single · bn · eval
**Q:** মোবাইল কোর্ট সর্বোচ্চ কত বছরের কারাদণ্ড দিতে পারে?  
**A:** দুই বছরের বেশি নয় (ধারা ৮(১))।  
> **[1025:39549] §৮ দণ্ড আরোপের সীমাবদ্ধতা** — ৮। (১) এই আইনের অধীন মোবাইল কোর্ট পরিচালনা করিয়া দণ্ড আরোপ করিবার ক্ষেত্রে, সংশ্লিষ্ট অপরাধের জন্য সংশ্লিষ্ট আইনে যে দণ্ডই নির্ধারিত থাকুক না কেন, দুই বছর এর অধিক কারাদণ্ড এই আইনের অধীন আরোপ করা যাইবে না।  (২) সংশ্লিষ্ট অপরাধের জন্য সংশ্লিষ্ট আইনে যে অর্থদণ্ড নির্ধারিত রহিয়াছে উক্ত অর্থদণ্ড বা অর্থদণ্ডে নির্ধারিত সীমার মধ্যে যে কোন পরিমাণ অর্থদণ্…

## sm01 · single · en · tune
**Q:** Can people smoke in public places or public transport?  
**A:** No. Smoking and using tobacco products in public places and public transport is prohibited (s.4).  
> **[927:27987] §৪ পাবলিক প্লেস এবং পাবলিক পরিবহণে [ধূমপান ও তামাকজাত দ্রব্য ব্যবহার] নিষিদ্ধ** — ৪। [(১) কোনো ব্যক্তি কোনো পাবলিক প্লেস এবং পাবলিক পরিবহণে ধূমপান ও তামাকজাত দ্রব্য ব্যবহার করিতে পারিবেন না:  তবে শর্ত থাকে যে, সরকার কোনো পাবলিক প্লেসে ধুমপানের জন্য এলাকা নির্দিষ্ট করিবার উদ্দেশ্যে প্রয়োজনীয় নির্দেশনা প্রদান করিতে পারিবে।]  [(২) কোন ব্যক্তি উপ-ধারা (১) এর বিধান লঙ্ঘন করিলে তিনি অনধিক [দুই হাজার টাকা] অর্থদণ্ডে দণ্ডনীয় হইবেন এব…

## rd01 · multi · bn · eval
**Q:** ড্রাইভিং লাইসেন্স ছাড়া গাড়ি চালালে কী শাস্তি হয়?  
**A:** অনধিক ৬ মাসের কারাদণ্ড বা অনধিক ২৫ হাজার টাকা অর্থদণ্ড বা উভয় দণ্ড (ধারা ৬৬); লাইসেন্স ছাড়া চালানো নিষিদ্ধ (ধারা ৪)।  
> **[1262:47918] §৬৬ ড্রাইভিং লাইসেন্স ব্যাতীত মোটরযান ও গণপরিবহণ চালনার বিধি-নিষেধ সংক্রান্ত ধারা ৪ এবং ৫ এর বিধান লঙ্ঘনের দণ্ড** — ৬৬। যদি কোনো ব্যক্তি ধারা ৪ এবং ৫ এর বিধান লঙ্ঘন করেন, তাহা হইলে উক্ত লঙ্ঘন হইবে একটি অপরাধ, এবং তজ্জন্য তিনি অনধিক ৬ (ছয়) মাসের কারাদণ্ড, বা অনধিক ২৫ (পঁচিশ) হাজার টাকা অর্থদণ্ড, বা উভয়দণ্ডে দণ্ডিত হইবেন।…
> **[1262:47805] §৪ ড্রাইভিং লাইসেন্স ব্যতীত মোটরযান চালনার উপর বিধি-নিষেধ** — ৪। (১) কোনো ব্যক্তি ড্রাইভিং লাইসেন্স বা, ক্ষেত্রমত, শিক্ষানবিশ ড্রাইভিং লাইসেন্স ব্যতীত বা মেয়াদোত্তীর্ণ লাইসেন্স ব্যবহার করিয়া পাবলিক প্লেসে কোনো মোটরযান চালাইতে বা চালাইবার অনুমতি প্রদান করিতে পারিবেন না।  (২) কোনো ব্যক্তি যে শ্রেণি বা ক্যাটাগরির মোটরযান চালনার লাইসেন্স প্রাপ্ত হইয়াছেন, সেই শ্রেণি বা ক্যাটাগরি ব্যতীত অন্য কোনো শ্রেণি বা ক্যাট…

## ml01 · single · en · eval
**Q:** What is the punishment for money laundering?  
**A:** Imprisonment of at least 4 and up to 12 years, plus a fine of up to twice the value of the property involved or 10 lakh taka, whichever is greater (s.4(2)).  
> **[1088:41800] §৪ মানিলন্ডারিং অপরাধ ও দণ্ড** — ৪। (১) এই আইনের উদ্দেশ্য পূরণকল্পে, মানিলন্ডারিং একটি অপরাধ বলিয়া গণ্য হইবে।  (২) কোন ব্যক্তি মানিলন্ডারিং অপরাধ করিলে বা মানিলন্ডারিং অপরাধ সংঘটনের চেষ্টা, সহায়তা বা ষড়যন্ত্র করিলে তিনি অন্যূন ৪ (চার) বৎসর এবং অনধিক ১২ (বার) বৎসর পর্যন্ত কারাদণ্ডে দণ্ডিত হইবেন এবং ইহার অতিরিক্ত অপরাধের সাথে সংশ্লিষ্ট সম্পত্তির দ্বিগুন মূল্যের সমপরিমাণ বা ১০ (দশ…

## dv01 · single · bn · tune
**Q:** পারিবারিক সহিংসতা বলতে কী বোঝায়?  
**A:** পারিবারিক সম্পর্ক আছে এমন কারও দ্বারা পরিবারের নারী বা শিশু সদস্যের উপর শারীরিক, মানসিক, যৌন নির্যাতন বা আর্থিক ক্ষতি (ধারা ৩)।  
> **[1063:40958] §৩ পারিবারিক সহিংসতা** — ৩। - এই আইনের উদ্দেশ্য পূরণকল্পে পারিবারিক সহিংসতা বলিতে পারিবারিক সম্পর্ক রহিয়াছে এমন কোন ব্যক্তি কর্তৃক পরিবারের অপর কোন নারী বা শিশু সদস্যের উপর শারীরিক নির্যাতন, মানসিক নির্যাতন, যৌন নির্যাতন অথবা আর্থিক ক্ষতিকে বুঝাইবে।  ব্যাখ্যা : এই ধারার উদ্দেশ্য পূরণকল্পে-  (ক) "শারীরিক নির্যাতন" অর্থে এমন কোন কাজ বা আচরণ করা, যাহা দ্বারা সংক্ষুব্ধ ব্যক্ত…

## dv02 · single · en · tune
**Q:** Can a court protect a woman from domestic violence?  
**A:** Yes. After hearing both sides, if satisfied that domestic violence occurred or is likely, the court may issue a protection order (s.14).  
> **[1063:40969] §১৪ সুরক্ষা আদেশ** — ১৪। সংক্ষুব্ধ ব্যক্তি ও প্রতিপক্ষকে শুনানীর সুযোগ প্রদান করিয়া আদালত যদি এই মর্মে সন্তুষ্ট হয় যে, পারিবারিক সহিংসতা ঘটিয়াছে বা ঘটিবার সম্ভাবনা রহিয়াছে, তাহা হইলে সংক্ষুব্ধ ব্যক্তির পক্ষে সুরক্ষা আদেশ প্রদান করিতে পারিবে এবং প্রতিপক্ষকে নিম্নবর্ণিত কাজ করা হইতে বিরত থাকিবার আদেশ প্রদান করিতে পারিবে, যথা :-  (ক) পারিবারিক সহিংসতামূলক কোন কাজ সংঘট…

## in01 · single · bn · eval
**Q:** বীমা দাবি দেরিতে পরিশোধ করলে বীমাকারীকে কী দিতে হয়?  
**A:** দাবি পরিশোধযোগ্য হওয়া বা সব আনুষ্ঠানিকতা পূরণের ৯০ দিনের মধ্যে পরিশোধ না করলে প্রচলিত ব্যাংক রেটের অতিরিক্ত ৫% হারে সুদ দিতে হয় (ধারা ৭২)।  
> **[1037:38283] §৭২ বিলম্বে দাবী পরিশোধের সুদ** — ৭২। (১) বীমাকারী কর্তৃক ইস্যুকৃত পলিসির অধীন অর্থ প্রদেয় হয় এবং দাবী প্রদানের জন্য সমস্ত কাগজপত্র দাবীদার কর্তৃক দাখিল করা হইয়াছে এইরূপ ক্ষেত্রে বীমাকারী যদি দাবী পরিশোধের প্রাপ্য হওয়া বা দাবীদার কর্তৃক সমস্ত আনুষ্ঠানিকতা পূরণের, যাহা পরে সংঘটিত হয়, ৯০ (নব্বই) দিনের মধ্যে দাবী পরিশোধে ব্যর্থ হয় তাহা হইলে উপ-ধারা (২) এ নির্ধারিত সুদ পরিশোধ করি…

## lg01 · single · bn · eval
**Q:** আইনগত সহায়তার জন্য কোথায় আবেদন করতে হয়?  
**A:** সুপ্রীম কোর্ট লিগ্যাল এইড কার্যালয় বা আঞ্চলিক, জেলা বা উপজেলা লিগ্যাল এইড কার্যালয়ে সরাসরি বা অনলাইনে (ধারা ১৬)।  
*note:* 2026 amended text  
> **[834:32504] §১৬ আইনগত সহায়তার জন্য আবেদন** — [১৬। (১) এই আইনের অধীন আইনগত সহায়তার জন্য সকল আবেদন অধিদপ্তরের অধীন সুপ্রীম কোর্ট লিগ্যাল এইড কার্যালয় বা আঞ্চলিক, জেলা বা উপজেলার লিগ্যাল এইড কার্যালয়ে সরাসরি বা অনলাইনে দাখিল করিতে পারিবে।  (২) এই আইনের অধীন কোনো আবেদন বা দরখাস্ত কোনো কার্যালয় কর্তৃক অগ্রাহ্য হইলে সংক্ষুদ্ধ বিচারপ্রার্থী উক্তরূপ সিদ্ধান্তের তারিখ হইতে ৬০ (ষাট) দিনের মধ্যে অধি…

## cr_c1 · single · en · eval
**Q:** How long does copyright last for a book?  
**A:** For a work published during the author's lifetime: the author's life plus 60 years after death (s.22, Copyright Act 2023).  
> **[1452:52648] §২২ প্রকাশিত সাহিত্য, নাটক, সংগীত ও শিল্পকর্মে কপিরাইটের মেয়াদ** — ২২। (১) প্রণেতার জীবনকালে প্রকাশিত কোনো সাহিত্য, নাটক, সংগীত বা শিল্পকর্মের (ফটোগ্রাফ ব্যতীত) কপিরাইট তাহার জীবদ্দশায় এবং তাহার মৃত্যুর পরবর্তী ৬০ (ষাট) বৎসর পর্যন্ত বিদ্যমান থাকিবে।  (২) প্রণেতার মৃত্যুর তারিখে কপিরাইট বিদ্যমান থাকে এইরূপ সাহিত্য, নাট্য বা সংগীত কর্ম বা খোদাই-কর্ম, বা অনুরূপ কর্মের যৌথ প্রণেতার ক্ষেত্রে, যিনি শেষে মৃত্যুবরণ করিয়…

## cy01 · single · bn · eval
**Q:** অনুমতি ছাড়া কারও কম্পিউটারে প্রবেশ করলে কী শাস্তি?  
**A:** বে-আইনি প্রবেশের জন্য অনধিক ১ বৎসর কারাদণ্ড বা অনধিক ১০ লক্ষ টাকা অর্থদণ্ড বা উভয়; অপরাধের উদ্দেশ্যে প্রবেশে অনধিক ২ বৎসর/২০ লক্ষ টাকা; হ্যাকিং করে তথ্য চুরি বা ক্ষতি করলে অনধিক ৫ বৎসর/৫০ লক্ষ টাকা (সাইবার সুরক্ষা আইন, ২০২৬, ধারা ১৮)।  
> **[1710:57959] §১৮ কম্পিউটার, ডিজিটাল ডিভাইস, কম্পিউটার সিস্টেম ইত্যাদিতে বে-আইনি প্রবেশ ও দণ্ড** — ১৮। (১) যদি কোনো ব্যক্তি ইচ্ছাকৃতভাবে—  (ক) কোনো কম্পিউটার, ডিজিটাল ডিভাইস, কম্পিউটার সিস্টেম, কম্পিউটার নেটওয়ার্কে বে-আইনি প্রবেশ করেন বা প্রবেশ করিতে সহায়তা করেন; বা  (খ) কোনো কম্পিউটার, ডিজিটাল ডিভাইস, কম্পিউটার সিস্টেম, কম্পিউটার নেটওয়ার্কে অপরাধ সংঘটনের উদ্দেশ্যে বে-আইনি প্রবেশ করেন বা প্রবেশ করিতে সহায়তা করেন; বা  (গ) কোনো কম্পিউটার, ডিজি…

## cy02 · single · en · eval
**Q:** Is blackmailing someone online a crime?  
**A:** Yes. Blackmailing, sexual harassment or publishing obscene content through a website or other digital medium is an offence (s.25, Cyber Protection Act 2026).  
> **[1710:57966] §২৫ যৌন হয়রানি, ব্ল্যাকমেইলিং বা অশ্লীল বিষয়বস্তু প্রকাশ সংক্রান্ত অপরাধ ও দণ্ড** — ২৫। (১) যদি কোনো ব্যক্তি ওয়েবসাইট বা অন্য কোনো ডিজিটাল বা ইলেকট্রনিক মাধ্যমে ইচ্ছাকৃতভাবে বা জ্ঞাতসারে অন্য কোনো ব্যক্তিকে ব্ল্যাকমেইলিং, বা যৌন হয়রানি, বা রিভেঞ্জ পর্ন, বা ডিজিটাল শিশু যৌন নিপীড়ন সংক্রান্ত উপাদান (চাইল্ড সেক্সুয়াল অ্যাবিউজ ম্যাটেরিয়াল) বা সেক্সটর্শন করিবার অভিপ্রায়ে সৃষ্ট, বা প্রাপ্ত, বা সংরক্ষিত কোনো তথ্য, ভিডিও চিত্র, অডিও…

## tx01 · single · bn · eval
**Q:** আয়কর রিটার্ন কাকে দাখিল করতে হয়?  
**A:** যার আয় করমুক্ত সীমা অতিক্রম করে বা ধারা ১৬৬-এ বর্ণিত অন্য শর্ত পূরণ হয়, তাকে উপকর কমিশনারের কাছে রিটার্ন দাখিল করতে হয়।  
> **[1429:51996] §১৬৬ রিটার্ন দাখিল** — ১৬৬। (১) প্রত্যেক ব্যক্তি উপকর কমিশনারের নিকট সংশ্লিষ্ট আয়বর্ষের জন্য রিটার্ন দাখিল করিবেন, যদি-  (ক) সংশ্লিষ্ট আয়বর্ষে তাহার আয় এই আইনের অধীন করমুক্ত আয়ের সীমা অতিক্রম করে;  (খ) সংশ্লিষ্ট আয়বর্ষের অব্যবহিত পূর্ববর্তী ৩ (তিন) বৎসরের মধ্যে কোনো বৎসর তাহার কর নির্ধারণ করা হয়;  (গ) উক্ত ব্যক্তি একটি কোম্পানি, কোনো শেয়ারহোল্ডার পরিচালক বা কোনো ক…

## id01 · single · en · tune
**Q:** Is every citizen entitled to a national ID card?  
**A:** Yes, every citizen is entitled to a national identity card and number, subject to the prescribed procedure and conditions (s.5).  
> **[1458:52889] §৫ জাতীয় পরিচয়পত্র ও জাতীয় পরিচিতি নম্বর পাইবার অধিকার, ইত্যাদি** — ৫। প্রত্যেক নাগরিক নির্ধারিত পদ্ধতি ও শর্ত সাপেক্ষে, জাতীয় পরিচয়পত্র ও জাতীয় পরিচিতি নম্বর পাইবার অধিকারী হইবেন।…

## gd01 · single · en · eval
**Q:** What does a court consider when appointing a guardian for a minor?  
**A:** The welfare of the minor, consistent with the law the minor is subject to — including age, sex, religion, the proposed guardian's character and the minor's own preference if old enough (s.17).  
> **[64:19374] §17 Matters to be considered by the Court in appointing guardian** — 17. (1) In appointing or declaring the guardian of a minor, the Court shall, subject to the provisions of this section, be guided by what, consistently with the law to which the minor is subject, appears in the circumstances to be for the welfare of the minor.  (2) In considering what will be for the welfare of the minor, the Court shall have regar…

## un01 · unanswerable · en · eval
**Q:** What is the current minimum wage for garment workers?  
*note:* Set by wage-board gazette notifications, not by the text of an Act in the corpus.  

## un02 · unanswerable · bn · eval
**Q:** বাংলাদেশ ব্যাংকের বর্তমান রেপো রেট কত?  
*note:* Monetary policy rate; not in any statute.  

## un03 · unanswerable · en · eval
**Q:** What did the High Court decide in the BLAST v Bangladesh case?  
*note:* Case law is not in the corpus.  

## un04 · unanswerable · en · tune
**Q:** How many days does it take to get a trade licence from Dhaka North City Corporation?  
*note:* Administrative service standard, not statutory text.  

## un05 · unanswerable · bn · eval
**Q:** ঢাকায় এখন জমি রেজিস্ট্রেশনের ফি কত টাকা?  
*note:* Fees are set by notification, not in the Act text.  

## un06 · unanswerable · en · eval
**Q:** What documents do I need to open a bank account?  
*note:* KYC circulars, not statutes.  

## un07 · unanswerable · bn · eval
**Q:** SSC পরীক্ষার ফলাফল কবে প্রকাশ হবে?  
*note:* Not a legal question.  

## un08 · unanswerable · en · tune
**Q:** What is the visa fee for Indian tourists visiting Bangladesh?  
*note:* Not in the corpus.  

## un09 · unanswerable · en · eval
**Q:** Which lawyer in Dhaka is best for divorce cases?  
*note:* Not in the corpus; also asks for a recommendation.  

## un10 · unanswerable · en · eval
**Q:** How many seats does the ruling party have in Parliament?  
*note:* Not statutory.  

## un11 · unanswerable · mixed · eval
**Q:** ইউরোপে পড়তে যাওয়ার জন্য IELTS এ কত স্কোর লাগে?  
*note:* Not in the corpus.  

## un12 · unanswerable · en · eval
**Q:** What is today's exchange rate between the taka and the US dollar?  
*note:* Not in the corpus.  
